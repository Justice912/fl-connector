from __future__ import annotations

import importlib.util
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .contracts import BridgeSetupCheck, BridgeSetupPlan
from .paths import FlPaths

ModuleChecker = Callable[[str], bool]
MidiPortProvider = Callable[[], tuple[list[str], list[str]]]


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def midi_ports() -> tuple[list[str], list[str]]:
    import mido  # type: ignore[import-not-found]

    return list(mido.get_input_names()), list(mido.get_output_names())


def default_flapi_server_source() -> Path:
    import flapi  # type: ignore[import-not-found]

    return Path(flapi.__file__).resolve().parent / "server"


def _check(
    *,
    key: str,
    label: str,
    ready: bool,
    ready_detail: str,
    missing_detail: str,
    action: str,
    blocking: bool = True,
) -> BridgeSetupCheck:
    return BridgeSetupCheck(
        key=key,
        label=label,
        status="ready" if ready else "missing",
        detail=ready_detail if ready else missing_detail,
        action="" if ready else action,
        blocking=blocking,
    )


def build_bridge_setup_plan(
    paths: FlPaths,
    *,
    module_checker: ModuleChecker = module_available,
    midi_port_provider: MidiPortProvider = midi_ports,
) -> BridgeSetupPlan:
    checks: list[BridgeSetupCheck] = []
    flapi_ready = module_checker("flapi")
    mido_ready = module_checker("mido")

    checks.append(
        _check(
            key="hardware_scripts",
            label="FL Studio Hardware scripts folder",
            ready=paths.hardware_scripts.exists(),
            ready_detail=str(paths.hardware_scripts),
            missing_detail=f"Missing folder: {paths.hardware_scripts}",
            action="Open FL Studio once or create the user data Settings > Hardware folder.",
        )
    )
    checks.append(
        _check(
            key="python_flapi",
            label="Flapi Python package",
            ready=flapi_ready,
            ready_detail="The backend can import flapi.",
            missing_detail="The backend cannot import flapi.",
            action="Run the backend dependency install command, then restart the backend.",
        )
    )
    checks.append(
        _check(
            key="python_mido",
            label="MIDI Python package",
            ready=mido_ready,
            ready_detail="The backend can import mido.",
            missing_detail="The backend cannot import mido.",
            action="Install the backend bridge dependencies, then restart the backend.",
        )
    )
    checks.append(
        _check(
            key="flapi_server_scripts",
            label="Flapi controller scripts",
            ready=paths.flapi_server_scripts.exists(),
            ready_detail=str(paths.flapi_server_scripts),
            missing_detail=f"Not installed at {paths.flapi_server_scripts}",
            action="Use Install Flapi Scripts after the backend can import flapi.",
        )
    )

    inputs: list[str] = []
    outputs: list[str] = []
    midi_error = ""
    if mido_ready:
        try:
            inputs, outputs = midi_port_provider()
        except Exception as exc:
            midi_error = str(exc)

    request_ready = any("Flapi Request" in port for port in outputs)
    response_ready = any("Flapi Response" in port for port in inputs)
    checks.append(
        _check(
            key="midi_request_port",
            label="Flapi Request MIDI output",
            ready=request_ready,
            ready_detail="Flapi Request is visible as a MIDI output.",
            missing_detail=midi_error or "Flapi Request is not visible as a MIDI output.",
            action="Create a loopMIDI port named Flapi Request.",
        )
    )
    checks.append(
        _check(
            key="midi_response_port",
            label="Flapi Response MIDI input",
            ready=response_ready,
            ready_detail="Flapi Response is visible as a MIDI input.",
            missing_detail=midi_error or "Flapi Response is not visible as a MIDI input.",
            action="Create a loopMIDI port named Flapi Response.",
        )
    )
    checks.append(
        BridgeSetupCheck(
            key="fl_studio_midi_settings",
            label="FL Studio MIDI settings",
            status="manual",
            detail="Enable Flapi Request and Flapi Response controller scripts inside FL Studio.",
            action=(
                "Open FL Studio > Options > MIDI Settings. Set the Flapi Request and "
                "Flapi Response ports, then choose their matching controller scripts."
            ),
            blocking=False,
        )
    )

    blocking_ready = all(check.status == "ready" for check in checks if check.blocking)
    can_install = flapi_ready and paths.hardware_scripts.exists() and not paths.flapi_server_scripts.exists()
    return BridgeSetupPlan(
        status="ready" if blocking_ready else "needs_action",
        message=(
            "Bridge setup checks are ready for a live read-only probe."
            if blocking_ready
            else "Bridge setup still needs a few local pieces before FL can respond."
        ),
        canInstallScripts=can_install,
        installCommand="/api/bridge/setup/install-scripts",
        manualSteps=[
            "Open FL Studio.",
            "Go to Options > MIDI Settings.",
            "Assign Flapi Request to the Flapi Request controller script.",
            "Assign Flapi Response to the Flapi Response controller script.",
            "Restart FL Studio, then refresh Bridge Health.",
        ],
        checks=checks,
    )


def install_bridge_server_scripts(
    paths: FlPaths,
    *,
    source_dir: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    source = source_dir or default_flapi_server_source()
    if not source.exists() or not source.is_dir():
        raise FileNotFoundError(f"Flapi server source folder not found: {source}")
    paths.hardware_scripts.mkdir(parents=True, exist_ok=True)
    if paths.flapi_server_scripts.exists():
        if not force:
            raise FileExistsError(str(paths.flapi_server_scripts))
        shutil.rmtree(paths.flapi_server_scripts)
    shutil.copytree(source, paths.flapi_server_scripts)
    return {
        "installed": True,
        "source": str(source),
        "target": str(paths.flapi_server_scripts),
        "force": force,
    }
