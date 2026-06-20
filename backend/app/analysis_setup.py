from __future__ import annotations

import importlib.util
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from .reconstruction_contracts import ReconstructionError

REQUIRED_PACKAGES = {
    "basic_pitch",
    "librosa",
    "numpy",
    "pyloudnorm",
    "scipy",
    "soundfile",
}


def worker_python(app_root: Path) -> Path:
    return Path(app_root) / ".analysis-worker" / "Scripts" / "python.exe"


def worker_requirements(app_root: Path) -> Path:
    return Path(app_root) / "backend" / "analysis-worker-requirements.txt"


def _default_lookup(name: str) -> str | None:
    return shutil.which(name)


def _default_package_probe(python: Path) -> list[str]:
    script = (
        "import importlib.util,json;"
        f"names={sorted(REQUIRED_PACKAGES)!r};"
        "print(json.dumps([name for name in names if importlib.util.find_spec(name)]))"
    )
    try:
        completed = subprocess.run(
            [str(python), "-c", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    import json

    try:
        return [str(name) for name in json.loads(completed.stdout)]
    except (TypeError, ValueError):
        return []


def build_analysis_setup_plan(
    app_root: Path,
    *,
    command_lookup: Callable[[str], str | None] = _default_lookup,
    package_probe: Callable[[Path], list[str]] = _default_package_probe,
) -> dict[str, object]:
    root = Path(app_root)
    python = worker_python(root)
    ffmpeg = command_lookup("ffmpeg")
    packages = set(package_probe(python)) if python.exists() else set()
    missing_packages = sorted(REQUIRED_PACKAGES - packages)

    checks = [
        {
            "id": "python311",
            "label": "Isolated Python 3.11 worker",
            "status": "ready" if python.exists() else "missing",
            "detail": str(python) if python.exists() else "Python 3.11 worker has not been created.",
        },
        {
            "id": "ffmpeg",
            "label": "FFmpeg audio decoder",
            "status": "ready" if ffmpeg else "missing",
            "detail": ffmpeg or "FFmpeg is not available on PATH.",
        },
        {
            "id": "workerPackages",
            "label": "Audio analysis packages",
            "status": "ready" if not missing_packages else "missing",
            "detail": (
                "All analysis packages are importable."
                if not missing_packages
                else "Missing: " + ", ".join(missing_packages)
            ),
        },
    ]
    ready = all(check["status"] == "ready" for check in checks)
    launcher = command_lookup("py")
    can_install = bool(launcher and ffmpeg and worker_requirements(root).exists()) and not ready
    return {
        "status": "ready" if ready else "needs_action",
        "ready": ready,
        "canInstall": can_install,
        "checks": checks,
        "manualSteps": [
            "Install official 64-bit Python 3.11 and confirm `py -3.11 --version` works.",
            "Install FFmpeg from an official source and confirm `ffmpeg -version` works.",
            "Return here and approve creation of the isolated analysis worker.",
        ],
        "workerPython": str(python),
    }


def install_analysis_worker(
    app_root: Path,
    *,
    approved: bool,
    command_lookup: Callable[[str], str | None] = _default_lookup,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, object]:
    if not approved:
        raise ReconstructionError("analysis worker installation requires explicit approval")

    root = Path(app_root)
    launcher = command_lookup("py")
    ffmpeg = command_lookup("ffmpeg")
    requirements = worker_requirements(root)
    if not launcher:
        raise ReconstructionError("Python launcher is missing; install official Python 3.11 first")
    if not ffmpeg:
        raise ReconstructionError("FFmpeg is missing; install it from an official source first")
    if not requirements.exists():
        raise ReconstructionError(f"worker requirements file is missing: {requirements}")

    python = worker_python(root)
    runner(
        [launcher, "-3.11", "--version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if not python.exists():
        runner(
            [launcher, "-3.11", "-m", "venv", str(python.parents[1])],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    runner(
        [str(python), "-m", "pip", "install", "-r", str(requirements)],
        check=True,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    return build_analysis_setup_plan(root, command_lookup=command_lookup)

