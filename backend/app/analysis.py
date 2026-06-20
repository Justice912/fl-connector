from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .contracts import Note
from .reconstruction_contracts import AnalysisSummary, ReconstructionError, StemRole

ProgressCallback = Callable[[int, str, str], None]


@dataclass(frozen=True)
class StemAnalysis:
    stemId: str
    role: StemRole
    confidence: float
    notes: list[Note]
    warnings: list[str]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "StemAnalysis":
        confidence = float(value.get("confidence", 0))
        if not 0 <= confidence <= 1:
            raise ReconstructionError("stem analysis confidence must be between 0 and 1")
        return cls(
            stemId=str(value["stemId"]),
            role=value.get("role", "other"),
            confidence=confidence,
            notes=[Note.from_dict(note) for note in value.get("notes", [])],
            warnings=[str(item) for item in value.get("warnings", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "stemId": self.stemId,
            "role": self.role,
            "confidence": self.confidence,
            "notes": [note.to_dict() for note in self.notes],
            "warnings": self.warnings,
        }


@dataclass(frozen=True)
class AnalysisResult:
    summary: AnalysisSummary
    stems: list[StemAnalysis]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AnalysisResult":
        result = cls(
            summary=AnalysisSummary.from_dict(value["summary"]),
            stems=[StemAnalysis.from_dict(item) for item in value.get("stems", [])],
        )
        if not result.stems:
            raise ReconstructionError("analysis result must include at least one stem")
        if len({item.stemId for item in result.stems}) != len(result.stems):
            raise ReconstructionError("analysis result stem IDs must be unique")
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary.to_dict(),
            "stems": [item.to_dict() for item in self.stems],
        }


class AnalysisProvider(Protocol):
    def analyze(self, project_path: Path, progress: ProgressCallback) -> AnalysisResult: ...


class LocalAnalysisProvider:
    def __init__(self, python: Path, backend_root: Path) -> None:
        self.python = Path(python)
        self.backend_root = Path(backend_root)

    def analyze(self, project_path: Path, progress: ProgressCallback) -> AnalysisResult:
        if not self.python.exists():
            raise ReconstructionError(f"analysis worker Python is missing: {self.python}")
        analysis_dir = Path(project_path) / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        result_path = analysis_dir / "worker-result.json"
        process = subprocess.Popen(
            [
                str(self.python),
                "-m",
                "analysis_worker.main",
                "--project",
                str(project_path),
                "--output",
                str(result_path),
            ],
            cwd=self.backend_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert process.stdout is not None
        for line in process.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "progress":
                progress(
                    int(event.get("progress", 0)),
                    str(event.get("stage", "analysis")),
                    str(event.get("message", "")),
                )
        _stdout, stderr = process.communicate()
        if process.returncode != 0:
            raise RuntimeError(stderr.strip() or f"analysis worker exited {process.returncode}")
        if not result_path.exists():
            raise RuntimeError("analysis worker did not create a result file")
        return AnalysisResult.from_dict(json.loads(result_path.read_text(encoding="utf-8")))

