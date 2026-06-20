from __future__ import annotations

from threading import Lock, Thread

from .analysis import AnalysisProvider
from .inventory import InventorySnapshot
from .reconstruction_compiler import ReconstructionCompiler
from .reconstruction_contracts import AnalysisJob, ReconstructionError, ReconstructionProject
from .reconstruction_store import ReconstructionStore


class AnalysisJobRunner:
    def __init__(
        self,
        store: ReconstructionStore,
        provider: AnalysisProvider,
        compiler: ReconstructionCompiler,
        *,
        inventory_provider=lambda: InventorySnapshot.empty(),
    ) -> None:
        self.store = store
        self.provider = provider
        self.compiler = compiler
        self.inventory_provider = inventory_provider
        self._lock = Lock()

    def run(self, project_id: str) -> ReconstructionProject:
        if not self._lock.acquire(blocking=False):
            raise ReconstructionError("another analysis job is already running")
        try:
            project = self.store.get(project_id)
            if not project.stems:
                raise ReconstructionError("upload at least one stem before analysis")
            attempt = project.analysisJob.attempt + 1 if project.analysisJob else 1
            job = AnalysisJob.create(attempt=attempt).with_progress(
                status="running",
                progress=1,
                stage="starting",
                message="Starting local audio analysis.",
            )
            project = self.store.save(project.with_changes(status="analyzing", analysisJob=job))

            def progress(value: int, stage: str, message: str) -> None:
                current = self.store.get(project_id)
                current_job = current.analysisJob or job
                self.store.save(
                    current.with_changes(
                        analysisJob=current_job.with_progress(
                            status="running",
                            progress=max(1, min(99, value)),
                            stage=stage,
                            message=message,
                        )
                    )
                )

            result = self.provider.analyze(self.store.project_dir(project_id), progress)
            current = self.store.get(project_id)
            if current.analysisOverrides:
                result = type(result).from_dict(
                    {
                        **result.to_dict(),
                        "summary": {
                            **result.summary.to_dict(),
                            **current.analysisOverrides,
                        },
                    }
                )
            compiled = self.compiler.compile(current, result, self.inventory_provider())
            complete_job = (compiled.analysisJob or job).with_progress(
                status="complete",
                progress=100,
                stage="complete",
                message="Analysis and FL blueprint are ready for review.",
            )
            return self.store.save(compiled.with_changes(status="review", analysisJob=complete_job))
        except Exception as exc:
            try:
                current = self.store.get(project_id)
                failed_job = (current.analysisJob or AnalysisJob.create()).with_progress(
                    status="error",
                    stage="error",
                    message="Local analysis failed.",
                    error=str(exc),
                )
                return self.store.save(current.with_changes(status="error", analysisJob=failed_job))
            except FileNotFoundError:
                raise exc
        finally:
            self._lock.release()

    def start(self, project_id: str) -> ReconstructionProject:
        current = self.store.get(project_id)
        if self._lock.locked():
            raise ReconstructionError("another analysis job is already running")
        thread = Thread(target=self.run, args=(project_id,), daemon=True)
        thread.start()
        return current

    def mark_interrupted_jobs(self) -> list[str]:
        changed = []
        for project in self.store.list_projects():
            if project.status != "analyzing" or not project.analysisJob:
                continue
            interrupted = project.analysisJob.with_progress(
                status="interrupted",
                stage="interrupted",
                message="Analysis was interrupted. Retry when ready.",
                error="Backend restarted while analysis was running.",
            )
            self.store.save(project.with_changes(status="error", analysisJob=interrupted))
            changed.append(project.id)
        return changed
