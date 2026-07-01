from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from app.reconstruction_contracts import ReconstructionError
from app.reconstruction_store import ReconstructionStore, UploadCandidate


def wav_bytes() -> bytes:
    return b"RIFF" + (40).to_bytes(4, "little") + b"WAVEfmt " + b"\x00" * 32


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    target = BytesIO()
    with ZipFile(target, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return target.getvalue()


def test_create_and_delete_owned_project(tmp_path: Path):
    store = ReconstructionStore(tmp_path)
    project = store.create_project("Midnight Township", rights_accepted=True)

    assert store.get(project.id).title == "Midnight Township"
    assert store.list_projects()[0].id == project.id

    store.delete(project.id)
    with pytest.raises(FileNotFoundError):
        store.get(project.id)


def test_upload_rejects_extension_spoofing(tmp_path: Path):
    store = ReconstructionStore(tmp_path)
    project = store.create_project("Owned", rights_accepted=True)

    with pytest.raises(ReconstructionError, match="signature"):
        store.add_uploads(
            project.id,
            [UploadCandidate(fileName="fake.wav", data=b"not wave audio")],
        )


def test_zip_upload_rejects_path_traversal(tmp_path: Path):
    store = ReconstructionStore(tmp_path)
    project = store.create_project("Owned", rights_accepted=True)

    with pytest.raises(ReconstructionError, match="unsafe ZIP path"):
        store.add_uploads(
            project.id,
            [UploadCandidate(fileName="stems.zip", data=zip_bytes({"../escape.wav": wav_bytes()}))],
        )


def test_zip_upload_persists_valid_stems_and_storage_size(tmp_path: Path):
    store = ReconstructionStore(tmp_path)
    project = store.create_project("Owned", rights_accepted=True)
    data = zip_bytes({"Drums.wav": wav_bytes(), "Bass.wav": wav_bytes()})

    updated = store.add_uploads(
        project.id,
        [UploadCandidate(fileName="suno-stems.zip", data=data)],
    )

    assert [stem.fileName for stem in updated.stems] == ["Bass.wav", "Drums.wav"]
    assert updated.status == "uploaded"
    assert updated.storageBytes == len(wav_bytes()) * 2
    assert (tmp_path / project.id / "input" / "Bass.wav").exists()


def test_extended_paths_are_under_project_dir(tmp_path):
    from app.reconstruction_store import ReconstructionStore

    store = ReconstructionStore(tmp_path / "reconstructions")
    project = store.create_project(title="Paths", rights_accepted=True)
    assert store.extended_dir(project.id) == store.project_dir(project.id) / "extended"
    assert store.extended_mix_path(project.id) == store.project_dir(project.id) / "extended" / "extended-mix.wav"

