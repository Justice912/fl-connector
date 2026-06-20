from pathlib import Path

from app.analysis import AnalysisResult
from app.analysis_jobs import AnalysisJobRunner
from app.inventory import InventorySnapshot
from app.reconstruction_compiler import ReconstructionCompiler
from app.reconstruction_store import ReconstructionStore, UploadCandidate


def wav_bytes() -> bytes:
    return b"RIFF" + (40).to_bytes(4, "little") + b"WAVEfmt " + b"\x00" * 32


class SuccessfulProvider:
    def analyze(self, project_path: Path, progress):
        project = __import__("json").loads((project_path / "project.json").read_text())
        stem = project["stems"][0]
        progress(35, "tempo", "Detected tempo")
        return AnalysisResult.from_dict(
            {
                "summary": {
                    "bpm": 114,
                    "bpmConfidence": 0.95,
                    "key": "G",
                    "scale": "minor",
                    "keyConfidence": 0.8,
                    "timeSignature": "4/4",
                    "durationSeconds": 8.42,
                    "sections": [],
                },
                "stems": [
                    {
                        "stemId": stem["id"],
                        "role": "bass",
                        "confidence": 0.9,
                        "notes": [{"pitch": 43, "startBeats": 0, "durationBeats": 1}],
                        "warnings": [],
                    }
                ],
            }
        )


class FailingProvider:
    def analyze(self, project_path: Path, progress):
        raise RuntimeError("worker crashed")


def project_with_stem(store: ReconstructionStore):
    project = store.create_project("Owned", rights_accepted=True)
    return store.add_uploads(
        project.id,
        [UploadCandidate(fileName="bass.wav", data=wav_bytes())],
    )


def test_job_runner_persists_progress_and_compiled_result(tmp_path: Path):
    store = ReconstructionStore(tmp_path)
    project = project_with_stem(store)
    runner = AnalysisJobRunner(
        store,
        SuccessfulProvider(),
        ReconstructionCompiler(),
        inventory_provider=lambda: InventorySnapshot.empty(),
    )

    completed = runner.run(project.id)

    assert completed.status == "review"
    assert completed.analysisJob.status == "complete"
    assert completed.analysisJob.progress == 100
    assert completed.analysisSummary.bpm == 114
    assert completed.parts[0].outputMode == "midi"


def test_job_runner_records_worker_failure(tmp_path: Path):
    store = ReconstructionStore(tmp_path)
    project = project_with_stem(store)
    runner = AnalysisJobRunner(
        store,
        FailingProvider(),
        ReconstructionCompiler(),
        inventory_provider=lambda: InventorySnapshot.empty(),
    )

    failed = runner.run(project.id)

    assert failed.status == "error"
    assert failed.analysisJob.status == "error"
    assert failed.analysisJob.error == "worker crashed"

