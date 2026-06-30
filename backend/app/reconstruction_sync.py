from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .bridge import probe_bridge, run_bridge_write
from .contracts import BridgeSnapshot
from .reconstruction_contracts import ReconstructionProject


@dataclass(frozen=True)
class SyncAssignment:
    index: int
    name: str

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "name": self.name}


@dataclass(frozen=True)
class SyncSkip:
    kind: str
    name: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "name": self.name, "message": self.message}


@dataclass(frozen=True)
class SyncPlan:
    tempo: int | None
    channels: list[SyncAssignment]
    mixer: list[SyncAssignment]
    skipped: list[SyncSkip]

    def is_empty(self) -> bool:
        return self.tempo is None and not self.channels and not self.mixer

    def fl_code(self) -> str:
        lines: list[str] = []
        if self.tempo is not None:
            value = int(round(self.tempo * 1000))
            lines.append("import general")
            lines.append("import midi")
            lines.append(
                f"general.processRECEvent(midi.REC_Tempo, {value}, "
                "midi.REC_Control | midi.REC_UpdateControl)"
            )
        if self.channels:
            lines.append("import channels")
            for item in self.channels:
                lines.append(
                    f"channels.setChannelName({item.index}, {json.dumps(item.name)}, useGlobalIndex=True)"
                )
        if self.mixer:
            lines.append("import mixer")
            for item in self.mixer:
                lines.append(f"mixer.setTrackName({item.index}, {json.dumps(item.name)})")
        return "\n".join(lines)


def build_sync_plan(project: ReconstructionProject, snapshot: BridgeSnapshot) -> SyncPlan:
    midi_parts = [part for part in project.parts if part.outputMode == "midi"]
    tempo = round(project.analysisSummary.bpm) if project.analysisSummary else None
    channel_count = snapshot.channelCount or 0
    track_count = snapshot.trackCount or 0
    channels: list[SyncAssignment] = []
    mixer: list[SyncAssignment] = []
    skipped: list[SyncSkip] = []
    for index, part in enumerate(midi_parts):
        if index < channel_count:
            channels.append(SyncAssignment(index=index, name=part.name))
        else:
            skipped.append(
                SyncSkip(
                    kind="channel",
                    name=part.name,
                    message=f"No channel at index {index} yet — add more channels in FL, then sync again.",
                )
            )
        insert = index + 1
        if insert <= track_count:
            mixer.append(SyncAssignment(index=insert, name=part.name))
        else:
            skipped.append(
                SyncSkip(
                    kind="mixer",
                    name=part.name,
                    message=f"No mixer insert at index {insert} yet.",
                )
            )
    return SyncPlan(tempo=tempo, channels=channels, mixer=mixer, skipped=skipped)


def _status_items(items: list[SyncAssignment], status: str) -> list[dict[str, Any]]:
    return [{"index": item.index, "name": item.name, "status": status} for item in items]


def apply_reconstruction_sync(
    project: ReconstructionProject,
    client_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    snapshot = probe_bridge(client_factory)
    if snapshot.status != "connected":
        return {
            "connected": False,
            "message": snapshot.message,
            "tempo": None,
            "channels": [],
            "mixer": [],
            "skipped": [],
            "bridge": snapshot.to_dict(),
        }
    plan = build_sync_plan(project, snapshot)
    if plan.is_empty():
        return {
            "connected": True,
            "message": "Nothing to sync yet — add channels/mixer tracks in FL, then sync again.",
            "tempo": None,
            "channels": [],
            "mixer": [],
            "skipped": [skip.to_dict() for skip in plan.skipped],
            "bridge": snapshot.to_dict(),
        }
    result = run_bridge_write(
        plan.fl_code(),
        "Synced FL session to the reconstruction.",
        client_factory,
    )
    status = "applied" if result.status == "connected" else "failed"
    return {
        "connected": True,
        "message": result.message,
        "tempo": {"value": plan.tempo, "status": status} if plan.tempo is not None else None,
        "channels": _status_items(plan.channels, status),
        "mixer": _status_items(plan.mixer, status),
        "skipped": [skip.to_dict() for skip in plan.skipped],
        "bridge": result.to_dict(),
    }
