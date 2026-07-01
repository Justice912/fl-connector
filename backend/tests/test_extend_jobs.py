from pathlib import Path

from app.extend_jobs import ExtendJobRunner
from app.reconstruction_store import ReconstructionStore, UploadCandidate


def _wav() -> bytes:
    return b"RIFF" + (40).to_bytes(4, "little") + b"WAVEfmt " + b"\x00" * 32


class FakeProvider:
    def extend(self, project_dir, options, progress):
        progress(50, "render", "halfway")
        return {"relativePath": "extended/extended-mix.wav", "durationSeconds": 390.0, "warnings": []}


def _project_with_stem(store):
    project = store.create_project(title="Extend", rights_accepted=True)
    store.add_uploads(project.id, [UploadCandidate(fileName="drums.wav", data=_wav())])
    return store.get(project.id)


def test_extend_runner_records_result(tmp_path):
    store = ReconstructionStore(tmp_path / "r")
    project = _project_with_stem(store)
    runner = ExtendJobRunner(store, FakeProvider())

    result = runner.run(project.id, {"genre": "amapiano", "targetSeconds": 390, "vocalMode": "place_once"})

    assert result.extendJob is not None and result.extendJob.status == "complete"
    assert result.extendedMix["relativePath"] == "extended/extended-mix.wav"
    assert result.extendedMix["durationSeconds"] == 390.0


def test_extend_runner_requires_stems(tmp_path):
    import pytest
    from app.reconstruction_contracts import ReconstructionError

    store = ReconstructionStore(tmp_path / "r")
    project = store.create_project(title="No stems", rights_accepted=True)
    runner = ExtendJobRunner(store, FakeProvider())
    with pytest.raises(ReconstructionError):
        runner.run(project.id, {"genre": "amapiano", "targetSeconds": 390, "vocalMode": "place_once"})


def test_extend_runner_marks_error_on_provider_failure(tmp_path):
    store = ReconstructionStore(tmp_path / "r")
    project = _project_with_stem(store)

    class Boom:
        def extend(self, project_dir, options, progress):
            raise RuntimeError("render blew up")

    result = ExtendJobRunner(store, Boom()).run(project.id, {"genre": "amapiano", "targetSeconds": 390, "vocalMode": "place_once"})
    assert result.extendJob.status == "error"
    assert "render blew up" in (result.extendJob.error or "")
