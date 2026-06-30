from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

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
