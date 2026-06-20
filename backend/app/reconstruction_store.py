from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from .reconstruction_contracts import ReconstructionError, ReconstructionProject, StemAsset

MAX_FILES = 20
MAX_PROJECT_BYTES = 1024 * 1024 * 1024
MAX_ZIP_RATIO = 200
ACCEPTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a"}
MEDIA_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
}


@dataclass(frozen=True)
class UploadCandidate:
    fileName: str
    data: bytes


class ReconstructionStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)

    def ensure(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def project_dir(self, project_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", project_id):
            raise FileNotFoundError(project_id)
        return self.base_dir / project_id

    def create_project(
        self,
        title: str,
        *,
        rights_accepted: bool,
        genre_profile: str = "south_african_dance",
    ) -> ReconstructionProject:
        project = ReconstructionProject.create(
            title=title,
            rightsAccepted=rights_accepted,
            genreProfile=genre_profile,
        )
        self.ensure()
        (self.project_dir(project.id) / "input").mkdir(parents=True, exist_ok=False)
        self.save(project)
        return project

    def save(self, project: ReconstructionProject) -> ReconstructionProject:
        project.validate()
        folder = self.project_dir(project.id)
        folder.mkdir(parents=True, exist_ok=True)
        self._atomic_json(folder / "project.json", project.to_dict())
        return project

    def get(self, project_id: str) -> ReconstructionProject:
        path = self.project_dir(project_id) / "project.json"
        if not path.exists():
            raise FileNotFoundError(project_id)
        return ReconstructionProject.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def stem_path(self, project_id: str, stem_id: str) -> tuple[Path, StemAsset]:
        project = self.get(project_id)
        stem = next((item for item in project.stems if item.id == stem_id), None)
        if stem is None:
            raise FileNotFoundError(stem_id)
        project_dir = self.project_dir(project_id).resolve()
        path = (project_dir / stem.relativePath).resolve()
        if project_dir not in path.parents or not path.is_file():
            raise FileNotFoundError(stem_id)
        return path, stem

    def list_projects(self) -> list[ReconstructionProject]:
        if not self.base_dir.exists():
            return []
        projects = []
        for path in self.base_dir.glob("*/project.json"):
            try:
                projects.append(
                    ReconstructionProject.from_dict(json.loads(path.read_text(encoding="utf-8")))
                )
            except (OSError, ValueError, KeyError):
                continue
        return sorted(projects, key=lambda item: item.updatedAt, reverse=True)

    def delete(self, project_id: str) -> None:
        folder = self.project_dir(project_id)
        if not (folder / "project.json").exists():
            raise FileNotFoundError(project_id)
        shutil.rmtree(folder)

    def clear_derived(self, project_id: str) -> ReconstructionProject:
        project = self.get(project_id)
        folder = self.project_dir(project_id)
        for name in ("analysis", "exports"):
            shutil.rmtree(folder / name, ignore_errors=True)
        updated = project.with_changes(
            status="uploaded" if project.stems else "draft",
            analysisJob=None,
            analysisSummary=None,
            parts=[],
            timeline=[],
            soundMatches=[],
            guideSteps=[],
            mixPlan=None,
            warnings=[],
        )
        return self.save(updated)

    def add_uploads(
        self,
        project_id: str,
        uploads: list[UploadCandidate],
    ) -> ReconstructionProject:
        project = self.get(project_id)
        expanded = self._expand_uploads(uploads)
        if len(project.stems) + len(expanded) > MAX_FILES:
            raise ReconstructionError(f"projects support at most {MAX_FILES} audio files")

        existing_names = {item.storedName.casefold() for item in project.stems}
        prepared: list[tuple[str, bytes]] = []
        for original_name, data in expanded:
            stored_name = self._safe_name(original_name)
            key = stored_name.casefold()
            if key in existing_names or any(name.casefold() == key for name, _ in prepared):
                raise ReconstructionError(f"duplicate stem file name: {stored_name}")
            self._validate_audio(stored_name, data)
            prepared.append((stored_name, data))

        added_bytes = sum(len(data) for _, data in prepared)
        if project.storageBytes + added_bytes > MAX_PROJECT_BYTES:
            raise ReconstructionError("project upload exceeds the 1 GB storage limit")

        folder = self.project_dir(project_id)
        input_dir = folder / "input"
        staging = folder / f".incoming-{uuid4()}"
        staging.mkdir(parents=False, exist_ok=False)
        new_stems: list[StemAsset] = []
        try:
            for stored_name, data in prepared:
                temp_path = staging / stored_name
                temp_path.write_bytes(data)
                new_stems.append(
                    StemAsset.create(
                        fileName=stored_name,
                        storedName=stored_name,
                        relativePath=f"input/{stored_name}",
                        mediaType=MEDIA_TYPES[Path(stored_name).suffix.lower()],
                        sizeBytes=len(data),
                        sha256=hashlib.sha256(data).hexdigest(),
                        role=self._infer_role(stored_name),
                    )
                )
            for stem in new_stems:
                os.replace(staging / stem.storedName, input_dir / stem.storedName)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        updated = project.with_changes(
            status="uploaded",
            stems=sorted([*project.stems, *new_stems], key=lambda item: item.fileName.casefold()),
            storageBytes=project.storageBytes + added_bytes,
        )
        return self.save(updated)

    def _expand_uploads(self, uploads: list[UploadCandidate]) -> list[tuple[str, bytes]]:
        expanded: list[tuple[str, bytes]] = []
        for upload in uploads:
            suffix = Path(upload.fileName).suffix.lower()
            if suffix != ".zip":
                expanded.append((upload.fileName, upload.data))
                continue
            if not upload.data.startswith(b"PK"):
                raise ReconstructionError(f"ZIP signature is invalid: {upload.fileName}")
            try:
                with ZipFile(BytesIO(upload.data)) as archive:
                    for info in archive.infolist():
                        if info.is_dir():
                            continue
                        pure = PurePosixPath(info.filename.replace("\\", "/"))
                        if pure.is_absolute() or ".." in pure.parts:
                            raise ReconstructionError(f"unsafe ZIP path: {info.filename}")
                        if info.file_size > MAX_PROJECT_BYTES:
                            raise ReconstructionError("ZIP entry exceeds the project size limit")
                        if info.compress_size and info.file_size / info.compress_size > MAX_ZIP_RATIO:
                            raise ReconstructionError("ZIP entry compression ratio is unsafe")
                        expanded.append((pure.name, archive.read(info)))
            except BadZipFile as exc:
                raise ReconstructionError(f"invalid ZIP archive: {upload.fileName}") from exc
        if not expanded:
            raise ReconstructionError("upload contains no audio files")
        return expanded

    @staticmethod
    def _safe_name(name: str) -> str:
        base = Path(name.replace("\\", "/")).name.strip()
        safe = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(" .")
        if not safe:
            raise ReconstructionError("stem file name is invalid")
        return safe

    @staticmethod
    def _validate_audio(name: str, data: bytes) -> None:
        suffix = Path(name).suffix.lower()
        if suffix not in ACCEPTED_AUDIO_EXTENSIONS:
            raise ReconstructionError(f"unsupported audio type: {suffix or 'missing extension'}")
        signatures = {
            ".wav": data.startswith(b"RIFF") and data[8:12] == b"WAVE",
            ".flac": data.startswith(b"fLaC"),
            ".mp3": data.startswith(b"ID3")
            or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0),
            ".m4a": len(data) >= 12 and data[4:8] == b"ftyp",
        }
        if not signatures[suffix]:
            raise ReconstructionError(f"audio signature does not match extension: {name}")

    @staticmethod
    def _infer_role(name: str):
        lowered = name.casefold()
        matches = [
            ("log", "log_drum"),
            ("drum", "drums"),
            ("perc", "percussion"),
            ("bass", "bass"),
            ("vocal", "vocals"),
            ("guitar", "guitar"),
            ("chord", "chords"),
            ("keys", "chords"),
            ("piano", "chords"),
            ("melody", "melody"),
            ("fx", "fx"),
        ]
        return next((role for token, role in matches if token in lowered), "other")

    @staticmethod
    def _atomic_json(path: Path, value: dict[str, object]) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(value, indent=2), encoding="utf-8")
        os.replace(temp, path)
