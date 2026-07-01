from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Protocol

from .reconstruction_contracts import AnalysisJob, ReconstructionError, ReconstructionProject
from .reconstruction_store import ReconstructionStore

Progress = Callable[[int, str, str], None]


class ExtendProvider(Protocol):
    def extend(self, project_dir: Path, options: dict[str, Any], progress: Progress) -> dict[str, Any]: ...


class LocalExtendProvider:
    def __init__(self, python: Path, backend_root: Path) -> None:
        self.python = Path(python)
        self.backend_root = Path(backend_root)

    def extend(self, project_dir: Path, options: dict[str, Any], progress: Progress) -> dict[str, Any]:
        if not self.python.exists():
            raise ReconstructionError(f"analysis worker Python is missing: {self.python}")
        extended_dir = Path(project_dir) / "extended"
        extended_dir.mkdir(parents=True, exist_ok=True)
        options_path = extended_dir / "options.json"
        options_path.write_text(json.dumps(options), encoding="utf-8")
        result_path = extended_dir / "result.json"
        process = subprocess.Popen(
            [str(self.python), "-m", "analysis_worker.extend",
             "--project", str(project_dir), "--options", str(options_path), "--output", str(result_path)],
            cwd=self.backend_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        assert process.stdout is not None
        for line in process.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "progress":
                progress(int(event.get("progress", 0)), str(event.get("stage", "extend")), str(event.get("message", "")))
        _stdout, stderr = process.communicate()
        if process.returncode != 0:
            raise RuntimeError(stderr.strip() or f"extend worker exited {process.returncode}")
        if not result_path.exists():
            raise RuntimeError("extend worker did not create a result file")
        return json.loads(result_path.read_text(encoding="utf-8"))


class ExtendJobRunner:
    def __init__(self, store: ReconstructionStore, provider: ExtendProvider) -> None:
        self.store = store
        self.provider = provider
        self._lock = Lock()

    def run(self, project_id: str, options: dict[str, Any]) -> ReconstructionProject:
        if not self._lock.acquire(blocking=False):
            raise ReconstructionError("another extend job is already running")
        try:
            project = self.store.get(project_id)
            if not project.stems:
                raise ReconstructionError("upload at least one stem before extending")
            job = AnalysisJob.create().with_progress(
                status="running", progress=1, stage="starting", message="Starting extended mix."
            )
            self.store.save(project.with_changes(extendJob=job))

            def progress(value: int, stage: str, message: str) -> None:
                current = self.store.get(project_id)
                self.store.save(current.with_changes(
                    extendJob=(current.extendJob or job).with_progress(
                        status="running", progress=max(1, min(99, value)), stage=stage, message=message)))

            result = self.provider.extend(self.store.project_dir(project_id), options, progress)
            current = self.store.get(project_id)
            done = (current.extendJob or job).with_progress(
                status="complete", progress=100, stage="complete", message="Extended mix ready.")
            return self.store.save(current.with_changes(extendJob=done, extendedMix=result))
        except ReconstructionError:
            raise
        except Exception as exc:
            current = self.store.get(project_id)
            failed = (current.extendJob or AnalysisJob.create()).with_progress(
                status="error", stage="error", message="Extended mix failed.", error=str(exc))
            return self.store.save(current.with_changes(extendJob=failed))
        finally:
            self._lock.release()

    def start(self, project_id: str, options: dict[str, Any]) -> ReconstructionProject:
        current = self.store.get(project_id)
        if self._lock.locked():
            raise ReconstructionError("another extend job is already running")
        Thread(target=self.run, args=(project_id, options), daemon=True).start()
        return current
