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


def test_setup_plan_can_bootstrap_missing_prerequisites_with_winget(tmp_path: Path):
    requirements = tmp_path / "backend" / "analysis-worker-requirements.txt"
    requirements.parent.mkdir(parents=True)
    requirements.write_text("basic-pitch==0.4.0\n", encoding="utf-8")

    plan = build_analysis_setup_plan(
        tmp_path,
        command_lookup=lambda name: "C:/Windows/winget.exe" if name == "winget" else None,
        package_probe=lambda _python: [],
    )

    assert plan["canInstall"] is True
    assert [item["id"] for item in plan["installPlan"]] == [
        "Python.Python.3.11",
        "Gyan.FFmpeg",
        "analysis-worker",
    ]


def test_install_bootstraps_verified_packages_and_worker(tmp_path: Path):
    requirements = tmp_path / "backend" / "analysis-worker-requirements.txt"
    requirements.parent.mkdir(parents=True)
    requirements.write_text("basic-pitch==0.4.0\n", encoding="utf-8")
    tools = {"winget": "C:/Windows/winget.exe", "py": "C:/Windows/py.exe"}
    calls: list[list[str]] = []

    def runner(command, **_kwargs):
        calls.append([str(item) for item in command])
        if command[1:3] == ["show", "--id"]:
            package_id = command[3]
            output = (
                "Publisher: Python Software Foundation\n"
                "Publisher Url: https://www.python.org/\n"
                "Installer Url: https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe\n"
                if package_id == "Python.Python.3.11"
                else "Publisher: Gyan\n"
                "License Url: https://www.ffmpeg.org/legal.html\n"
                "Installer Url: https://github.com/GyanD/codexffmpeg/releases/download/8.1.1/ffmpeg.zip\n"
            )
            return type("Completed", (), {"stdout": output})()
        if command[1:3] == ["install", "--id"]:
            if command[3] == "Gyan.FFmpeg":
                tools["ffmpeg"] = "C:/WinGet/Links/ffmpeg.exe"
            return type("Completed", (), {"stdout": "installed"})()
        if command[1:3] == ["-3.11", "--version"]:
            if not any(call[1:4] == ["install", "--id", "Python.Python.3.11"] for call in calls):
                raise RuntimeError("Python 3.11 is not installed")
            return type("Completed", (), {"stdout": "Python 3.11.9"})()
        if command[1:4] == ["-3.11", "-m", "venv"]:
            python = tmp_path / ".analysis-worker" / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"python")
        return type("Completed", (), {"stdout": "ok"})()

    result = install_analysis_worker(
        tmp_path,
        approved=True,
        command_lookup=lambda name: tools.get(name),
        package_probe=lambda _python: [
            "basic_pitch",
            "librosa",
            "numpy",
            "pyloudnorm",
            "scipy",
            "soundfile",
        ],
        runner=runner,
    )

    assert result["ready"] is True
    assert any(call[1:4] == ["install", "--id", "Python.Python.3.11"] for call in calls)
    assert any(call[1:4] == ["install", "--id", "Gyan.FFmpeg"] for call in calls)
    assert any(call[-2:] == ["-r", str(requirements)] for call in calls)


def test_install_rejects_unexpected_package_metadata(tmp_path: Path):
    requirements = tmp_path / "backend" / "analysis-worker-requirements.txt"
    requirements.parent.mkdir(parents=True)
    requirements.write_text("basic-pitch==0.4.0\n", encoding="utf-8")

    def runner(command, **_kwargs):
        if command[1:3] == ["-3.11", "--version"]:
            raise RuntimeError("missing")
        return type("Completed", (), {"stdout": "Publisher: Unknown\nInstaller Url: https://example.com/a.exe"})()

    with pytest.raises(ReconstructionError, match="metadata verification failed"):
        install_analysis_worker(
            tmp_path,
            approved=True,
            command_lookup=lambda name: {
                "winget": "C:/Windows/winget.exe",
                "py": "C:/Windows/py.exe",
            }.get(name),
            runner=runner,
        )
