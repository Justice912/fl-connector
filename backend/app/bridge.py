from __future__ import annotations

import json
from collections.abc import Callable
from importlib import import_module
from threading import Lock
from typing import Any

from .contracts import BridgeSnapshot

SETUP_STEPS = [
    "Install Flapi in the backend Python environment.",
    "Create loopMIDI ports named Flapi Request and Flapi Response.",
    "Install and enable the Flapi Request and Flapi Response controller scripts in FL Studio MIDI settings.",
    "Restart FL Studio, then refresh this bridge health panel.",
]

FLAPI_RESPONSE_TIMEOUT_SECONDS = 3.0
SNAPSHOT_VARIABLE = "__fl_connector_bridge_snapshot__"
SNAPSHOT_SCALAR_KEYS = [
    "flVersion",
    "projectTitle",
    "selectedTrack",
    "trackCount",
    "transport",
]
TRANSPORT_ACTIONS = {
    "play": "transport.start()",
    "stop": "transport.stop()",
}
_BRIDGE_PROBE_LOCK = Lock()

READ_ONLY_FL_PROBE = """
import mixer
import plugins
import transport
import ui

def _safe(label, fn, fallback=None):
    try:
        return fn()
    except Exception as exc:
        __fl_connector_bridge_errors__.append(label + ": " + str(exc))
        return fallback

def _slot_names(track_index):
    names = []
    for slot_index in range(10):
        valid = _safe(
            "plugins.isValid(" + str(track_index) + "," + str(slot_index) + ")",
            lambda: plugins.isValid(track_index, slot_index),
            False,
        )
        if not valid:
            continue
        name = _safe(
            "plugins.getPluginName(" + str(track_index) + "," + str(slot_index) + ")",
            lambda: plugins.getPluginName(track_index, slot_index),
            "",
        )
        if name:
            names.append(str(name))
    return names

__fl_connector_bridge_errors__ = []
track_count = _safe("mixer.trackCount", mixer.trackCount, 0) or 0
selected_track = _safe("mixer.trackNumber", mixer.trackNumber, None)
tracks = []

for track_index in range(min(int(track_count), 16)):
    tracks.append({
        "index": track_index,
        "name": _safe("mixer.getTrackName(" + str(track_index) + ")", lambda: mixer.getTrackName(track_index), ""),
        "volume": _safe("mixer.getTrackVolume(" + str(track_index) + ")", lambda: mixer.getTrackVolume(track_index), None),
        "pan": _safe("mixer.getTrackPan(" + str(track_index) + ")", lambda: mixer.getTrackPan(track_index), None),
        "selected": bool(_safe("mixer.isTrackSelected(" + str(track_index) + ")", lambda: mixer.isTrackSelected(track_index), False)),
        "slots": _slot_names(track_index),
    })

__fl_connector_bridge_snapshot__ = {
    "flVersion": _safe("ui.getVersion", lambda: ui.getVersion(4), None),
    "projectTitle": _safe("ui.getProgTitle", ui.getProgTitle, None),
    "selectedTrack": selected_track,
    "trackCount": track_count,
    "transport": {
        "playing": bool(_safe("transport.isPlaying", transport.isPlaying, False)),
        "recording": bool(_safe("transport.isRecording", transport.isRecording, False)),
        "loopMode": int(_safe("transport.getLoopMode", transport.getLoopMode, 0) or 0),
        "songPosition": float(_safe("transport.getSongPos", transport.getSongPos, 0.0) or 0.0),
        "songPositionHint": str(_safe("transport.getSongPosHint", transport.getSongPosHint, "")),
        "songLengthBars": _safe("transport.getSongLength(3)", lambda: transport.getSongLength(3), None),
        "tempo": _safe("mixer.getCurrentTempo", mixer.getCurrentTempo, None),
    },
    "tracks": tracks,
    "errors": __fl_connector_bridge_errors__,
}
""".strip()


def _extend_flapi_timeout(flapi_module: Any) -> None:
    consts = getattr(flapi_module, "_consts", None)
    if consts is not None and hasattr(consts, "TIMEOUT_DURATION"):
        consts.TIMEOUT_DURATION = FLAPI_RESPONSE_TIMEOUT_SECONDS


def _close_open_flapi_context() -> None:
    try:
        context_module = import_module("flapi.__context")
        decorate_module = import_module("flapi.__decorate")
        context = context_module.pop_context()
    except Exception:
        return

    for port_name in ("req_port", "res_port"):
        close = getattr(getattr(context, port_name, None), "close", None)
        if callable(close):
            close()

    restore = getattr(decorate_module, "restore_original_functions", None)
    functions_backup = getattr(context, "functions_backup", None)
    if callable(restore) and functions_backup is not None:
        restore(functions_backup)


def _snapshot_key_expression(key: str) -> str:
    return f'{SNAPSHOT_VARIABLE}["{key}"]'


def _normalize_transport_snapshot(transport: dict[str, Any] | None) -> dict[str, Any] | None:
    if not transport:
        return transport
    tempo = transport.get("tempo")
    if tempo is None:
        return transport
    scaled_tempo = float(tempo) / 1000
    if float(tempo) > 240 and 40 <= scaled_tempo <= 240:
        return {**transport, "tempo": scaled_tempo}
    return transport


def _read_bridge_snapshot(client: Any) -> dict[str, Any]:
    snapshot = {key: client.eval(_snapshot_key_expression(key)) for key in SNAPSHOT_SCALAR_KEYS}
    snapshot["transport"] = _normalize_transport_snapshot(snapshot.get("transport"))
    track_count = int(client.eval(f'len({SNAPSHOT_VARIABLE}["tracks"])') or 0)
    snapshot["tracks"] = [
        client.eval(f'{SNAPSHOT_VARIABLE}["tracks"][{track_index}]')
        for track_index in range(track_count)
    ]
    snapshot["errors"] = client.eval(_snapshot_key_expression("errors")) or []
    return snapshot


def _connected_snapshot(message: str, raw_snapshot: dict[str, Any]) -> BridgeSnapshot:
    return BridgeSnapshot.from_dict(
        {
            "status": "connected",
            "message": message,
            "source": "flapi",
            "setup": [],
            **raw_snapshot,
        }
    )


def default_client_factory() -> Any:
    import flapi  # type: ignore[import-not-found]

    class FlapiModuleClient:
        def __init__(self) -> None:
            _extend_flapi_timeout(flapi)
            if not flapi.enable():
                _close_open_flapi_context()
                raise RuntimeError(
                    "Flapi MIDI ports opened, but FL Studio did not answer the hello message. "
                    "In FL Studio, press Options > MIDI Settings > Update MIDI scripts, then refresh the bridge. "
                    "If it still does not answer, restart FL Studio."
                )

        def exec(self, code: str) -> None:
            flapi.fl_exec(code)

        def eval(self, expression: str) -> Any:
            return flapi.fl_eval(expression)

        def close(self) -> None:
            flapi.disable()

    return FlapiModuleClient()


def _disconnected(message: str, errors: list[str] | None = None) -> BridgeSnapshot:
    return BridgeSnapshot.from_dict(
        {
            "status": "disconnected",
            "message": message,
            "source": "flapi",
            "transport": None,
            "tracks": [],
            "setup": SETUP_STEPS,
            "errors": errors or [],
        }
    )


def _error(message: str, errors: list[str] | None = None) -> BridgeSnapshot:
    return BridgeSnapshot.from_dict(
        {
            "status": "error",
            "message": message,
            "source": "flapi",
            "transport": None,
            "tracks": [],
            "setup": SETUP_STEPS,
            "errors": errors or [],
        }
    )


def probe_bridge(
    client_factory: Callable[[], Any] | None = None,
) -> BridgeSnapshot:
    factory = client_factory or default_client_factory
    client: Any | None = None
    with _BRIDGE_PROBE_LOCK:
        try:
            client = factory()
        except ModuleNotFoundError as exc:
            return _disconnected(
                "Flapi Python package is not importable in this backend environment.",
                [str(exc)],
            )
        except Exception as exc:
            return _disconnected(
                "Flapi could not connect to FL Studio. Check MIDI ports and controller scripts.",
                [str(exc)],
            )

        try:
            client.exec(READ_ONLY_FL_PROBE)
            raw_snapshot = _read_bridge_snapshot(client)
            return _connected_snapshot(
                "Live FL bridge responded with a read-only snapshot.",
                raw_snapshot,
            )
        except Exception as exc:
            return _error(
                "Flapi connected, but the read-only FL snapshot probe failed.",
                [str(exc)],
            )
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()


def run_bridge_write(
    fl_code: str,
    message: str,
    client_factory: Callable[[], Any] | None = None,
) -> BridgeSnapshot:
    factory = client_factory or default_client_factory
    client: Any | None = None
    with _BRIDGE_PROBE_LOCK:
        try:
            client = factory()
        except ModuleNotFoundError as exc:
            return _disconnected(
                "Flapi Python package is not importable in this backend environment.",
                [str(exc)],
            )
        except Exception as exc:
            return _disconnected(
                "Flapi could not connect to FL Studio. Check MIDI ports and controller scripts.",
                [str(exc)],
            )

        try:
            client.exec(fl_code)
            client.exec(READ_ONLY_FL_PROBE)
            raw_snapshot = _read_bridge_snapshot(client)
            return _connected_snapshot(message, raw_snapshot)
        except Exception as exc:
            return _error(
                "Flapi connected, but the live write action failed.",
                [str(exc)],
            )
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()


def run_transport_action(
    action: str,
    client_factory: Callable[[], Any] | None = None,
) -> BridgeSnapshot:
    command = TRANSPORT_ACTIONS.get(action)
    if command is None:
        raise ValueError(f"unsupported transport action: {action}")
    return run_bridge_write(
        f"import transport\n{command}",
        f"Live FL transport action applied: {action}.",
        client_factory=client_factory,
    )


def set_project_tempo(
    bpm: float,
    client_factory: Callable[[], Any] | None = None,
) -> BridgeSnapshot:
    if not 40 <= bpm <= 240:
        raise ValueError("bpm must be between 40 and 240")
    value = int(round(bpm * 1000))
    fl_code = (
        "import general\n"
        "import midi\n"
        f"general.processRECEvent(midi.REC_Tempo, {value}, midi.REC_Control | midi.REC_UpdateControl)"
    )
    return run_bridge_write(fl_code, f"Set FL project tempo to {bpm:g} BPM.", client_factory=client_factory)


def set_mixer_track(
    index: int,
    *,
    name: str | None = None,
    volume: float | None = None,
    pan: float | None = None,
    client_factory: Callable[[], Any] | None = None,
) -> BridgeSnapshot:
    if not 0 <= index <= 125:
        raise ValueError("mixer track index must be between 0 and 125")
    if name is None and volume is None and pan is None:
        raise ValueError("provide at least one of name, volume, or pan")
    lines = ["import mixer"]
    changed: list[str] = []
    if name is not None:
        if not name.strip() or len(name) > 100:
            raise ValueError("track name must be 1-100 characters")
        lines.append(f"mixer.setTrackName({index}, {json.dumps(name)})")
        changed.append("name")
    if volume is not None:
        if not 0 <= volume <= 1:
            raise ValueError("volume must be between 0 and 1")
        lines.append(f"mixer.setTrackVolume({index}, {round(volume, 4)})")
        changed.append("volume")
    if pan is not None:
        if not -1 <= pan <= 1:
            raise ValueError("pan must be between -1 and 1")
        lines.append(f"mixer.setTrackPan({index}, {round(pan, 4)})")
        changed.append("pan")
    message = f"Updated FL mixer track {index} ({', '.join(changed)})."
    return run_bridge_write("\n".join(lines), message, client_factory=client_factory)
