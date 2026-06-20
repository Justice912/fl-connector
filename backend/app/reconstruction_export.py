from __future__ import annotations

import json
import re
import struct
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from .contracts import NotePayload
from .reconstruction_contracts import ReconstructionProject

PPQ = 480


def midi_bytes(payload: NotePayload) -> bytes:
    payload.validate()
    events: list[tuple[int, int, bytes]] = []
    tempo = round(60_000_000 / payload.bpm)
    events.append((0, 0, b"\xff\x51\x03" + tempo.to_bytes(3, "big")))
    events.append((0, 0, b"\xff\x58\x04\x04\x02\x18\x08"))
    title = payload.title.encode("utf-8")[:127]
    events.append((0, 0, b"\xff\x03" + _variable_length(len(title)) + title))
    for note in payload.notes:
        start = max(0, round(note.startBeats * PPQ))
        end = max(start + 1, round((note.startBeats + note.durationBeats) * PPQ))
        velocity = max(1, min(127, round(note.velocity * 127)))
        events.append((start, 1, bytes((0x90, note.pitch, velocity))))
        events.append((end, 0, bytes((0x80, note.pitch, 0))))
    track = bytearray()
    previous_tick = 0
    for tick, order, event in sorted(events, key=lambda item: (item[0], item[1])):
        del order
        track.extend(_variable_length(tick - previous_tick))
        track.extend(event)
        previous_tick = tick
    track.extend(b"\x00\xff\x2f\x00")
    header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, PPQ)
    return header + b"MTrk" + struct.pack(">I", len(track)) + bytes(track)


def build_reconstruction_export(project: ReconstructionProject, project_dir: Path) -> bytes:
    target = BytesIO()
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("project.json", _json(project.to_dict()))
        archive.writestr(
            "analysis.json",
            _json(project.analysisSummary.to_dict() if project.analysisSummary else None),
        )
        archive.writestr("arrangement.json", _json([item.to_dict() for item in project.timeline]))
        archive.writestr("mix-plan.json", _json(project.mixPlan))
        archive.writestr(
            "recommendations.json",
            _json([item.to_dict() for item in project.soundMatches]),
        )
        archive.writestr(
            "guide-manifest.json",
            _json([item.to_dict() for item in project.guideSteps]),
        )
        for part in project.parts:
            if part.outputMode == "midi":
                for pattern in part.patterns:
                    archive.writestr(
                        f"midi/{_safe(part.name)}/{_safe(pattern.name)}.mid",
                        midi_bytes(pattern.payload),
                    )
            elif part.approved and part.audioRelativePath:
                source = Path(project_dir) / part.audioRelativePath
                if source.exists():
                    archive.write(source, f"audio/{_safe(source.name)}")
    return target.getvalue()


def _variable_length(value: int) -> bytes:
    buffer = value & 0x7F
    output = bytearray((buffer,))
    while value >> 7:
        value >>= 7
        output.insert(0, (value & 0x7F) | 0x80)
    return bytes(output)


def _json(value) -> str:
    return json.dumps(value, indent=2)


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._ -]", "_", value).strip(" .") or "item"
