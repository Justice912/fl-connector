from __future__ import annotations

import importlib.util
import os
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
BOOTSTRAP_PACKAGES = (
    {
        "id": "Python.Python.3.11",
        "name": "Python 3.11",
        "publisher": "Python Software Foundation",
        "source": "winget",
        "requiredMetadata": (
            "Publisher: Python Software Foundation",
            "Publisher Url: https://www.python.org/",
            "Installer Url: https://www.python.org/",
        ),
    },
    {
        "id": "Gyan.FFmpeg",
        "name": "FFmpeg Windows build",
        "publisher": "Gyan",
        "source": "winget",
        "requiredMetadata": (
            "Publisher: Gyan",
            "License Url: https://www.ffmpeg.org/legal.html",
            "Installer Url: https://github.com/GyanD/codexffmpeg/",
        ),
    },
)


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


def _public_install_plan() -> list[dict[str, str]]:
    return [
        {
            "id": str(package["id"]),
            "name": str(package["name"]),
            "publisher": str(package["publisher"]),
            "source": str(package["source"]),
        }
        for package in BOOTSTRAP_PACKAGES
    ] + [
        {
            "id": "analysis-worker",
            "name": "Pinned local analysis worker",
            "publisher": "FL Connector",
            "source": "backend/analysis-worker-requirements.txt",
        }
    ]


def _python311_available(
    launcher: str | None,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> bool:
    if not launcher:
        return False
    try:
        runner(
            [launcher, "-3.11", "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return False
    return True


def _bootstrap_package(
    winget: str,
    package: dict[str, object],
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    package_id = str(package["id"])
    try:
        metadata = runner(
            [
                winget,
                "show",
                "--id",
                package_id,
                "--exact",
                "--source",
                "winget",
                "--accept-source-agreements",
                "--disable-interactivity",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        ).stdout
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        raise ReconstructionError(f"could not verify winget metadata for {package_id}: {exc}") from exc
    missing = [token for token in package["requiredMetadata"] if token not in metadata]
    if missing:
        raise ReconstructionError(
            f"winget metadata verification failed for {package_id}: missing {', '.join(missing)}"
        )
    try:
        runner(
            [
                winget,
                "install",
                "--id",
                package_id,
                "--exact",
                "--source",
                "winget",
                "--silent",
                "--accept-package-agreements",
                "--accept-source-agreements",
                "--disable-interactivity",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        raise ReconstructionError(f"winget could not install {package_id}: {exc}") from exc


def _refresh_winget_path() -> None:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return
    links = str(Path(local) / "Microsoft" / "WinGet" / "Links")
    entries = os.environ.get("PATH", "").split(os.pathsep)
    if links.casefold() not in {entry.casefold() for entry in entries}:
        os.environ["PATH"] = os.pathsep.join([links, *entries])


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
    winget = command_lookup("winget")
    requirements_exist = worker_requirements(root).exists()
    can_install = bool(requirements_exist and not ready and (winget or (launcher and ffmpeg)))
    return {
        "status": "ready" if ready else "needs_action",
        "ready": ready,
        "canInstall": can_install,
        "bootstrapMethod": "winget" if winget else "existing-tools",
        "installPlan": _public_install_plan(),
        "checks": checks,
        "manualSteps": [
            "Review the listed publishers and approve the local installation.",
            "Windows Package Manager installs missing prerequisites from its winget source.",
            "The connector creates an isolated Python 3.11 worker and runs compatibility checks.",
        ],
        "workerPython": str(python),
    }


def install_analysis_worker(
    app_root: Path,
    *,
    approved: bool,
    command_lookup: Callable[[str], str | None] = _default_lookup,
    package_probe: Callable[[Path], list[str]] = _default_package_probe,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, object]:
    if not approved:
        raise ReconstructionError("analysis worker installation requires explicit approval")

    root = Path(app_root)
    launcher = command_lookup("py")
    ffmpeg = command_lookup("ffmpeg")
    winget = command_lookup("winget")
    requirements = worker_requirements(root)
    if not requirements.exists():
        raise ReconstructionError(f"worker requirements file is missing: {requirements}")

    if not _python311_available(launcher, runner):
        if not winget:
            raise ReconstructionError("Python 3.11 is missing and winget is unavailable")
        _bootstrap_package(winget, BOOTSTRAP_PACKAGES[0], runner)
        launcher = command_lookup("py")
        if not _python311_available(launcher, runner):
            raise ReconstructionError("Python 3.11 installation did not pass its version check")

    if not ffmpeg:
        if not winget:
            raise ReconstructionError("FFmpeg is missing and winget is unavailable")
        _bootstrap_package(winget, BOOTSTRAP_PACKAGES[1], runner)
        _refresh_winget_path()
        ffmpeg = command_lookup("ffmpeg")
        if not ffmpeg:
            raise ReconstructionError("FFmpeg installation completed but ffmpeg is not available on PATH")

    python = worker_python(root)
    assert launcher is not None
    if not python.exists():
        try:
            runner(
                [launcher, "-3.11", "-m", "venv", str(python.parents[1])],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            raise ReconstructionError(f"could not create the Python 3.11 worker: {exc}") from exc
    try:
        runner(
            [str(python), "-m", "pip", "install", "-r", str(requirements)],
            check=True,
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        raise ReconstructionError(f"analysis worker package installation failed: {exc}") from exc
    plan = build_analysis_setup_plan(
        root,
        command_lookup=command_lookup,
        package_probe=package_probe,
    )
    if not plan["ready"]:
        missing = [check["label"] for check in plan["checks"] if check["status"] != "ready"]
        raise ReconstructionError(
            "analysis worker compatibility checks failed: " + ", ".join(missing)
        )
    return plan
