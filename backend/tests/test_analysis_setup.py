from pathlib import Path

import pytest

from app.analysis_setup import build_analysis_setup_plan, install_analysis_worker
from app.reconstruction_contracts import ReconstructionError


def test_setup_plan_reports_missing_worker_and_ffmpeg(tmp_path: Path):
    plan = build_analysis_setup_plan(
        tmp_path,
        command_lookup=lambda _name: None,
        package_probe=lambda _python: [],
    )

    assert plan["status"] == "needs_action"
    assert plan["ready"] is False
    assert {check["id"] for check in plan["checks"] if check["status"] == "missing"} == {
        "python311",
        "ffmpeg",
        "workerPackages",
    }
    assert plan["canInstall"] is False


def test_setup_plan_is_ready_when_tools_and_packages_exist(tmp_path: Path):
    python = tmp_path / ".analysis-worker" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"python")

    plan = build_analysis_setup_plan(
        tmp_path,
        command_lookup=lambda name: "C:/tools/ffmpeg.exe" if name == "ffmpeg" else None,
        package_probe=lambda _python: [
            "basic_pitch",
            "librosa",
            "numpy",
            "pyloudnorm",
            "scipy",
            "soundfile",
        ],
    )

    assert plan["status"] == "ready"
    assert plan["ready"] is True
    assert all(check["status"] == "ready" for check in plan["checks"])


def test_install_requires_explicit_approval(tmp_path: Path):
    with pytest.raises(ReconstructionError, match="explicit approval"):
        install_analysis_worker(tmp_path, approved=False)

