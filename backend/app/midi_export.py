from __future__ import annotations

from dataclasses import replace

from .contracts import Note, NotePayload, SongDraft
from .reconstruction_contracts import ReconstructionProject

PPQ = 96


def _vlq(value: int) -> bytes:
    if value < 0:
        raise ValueError("variable-length quantity must be non-negative")
    chunks = [value & 0x7F]
    value >>= 7
    while value:
        chunks.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(chunks))


def _note_events(notes: list[Note], channel: int) -> list[tuple[int, int, int, int, int]]:
    events: list[tuple[int, int, int, int, int]] = []
    for note in notes:
        if note.muted:
            continue
        start = max(0, round(note.startBeats * PPQ))
        duration = max(1, round(note.durationBeats * PPQ))
        pitch = max(0, min(127, int(note.pitch)))
        velocity = max(1, min(127, round(note.velocity * 127)))
        # order 1 = note-on, 0 = note-off, so note-off sorts first at equal ticks
        events.append((start, 1, 0x90 | channel, pitch, velocity))
        events.append((start + duration, 0, 0x80 | channel, pitch, 0))
    events.sort(key=lambda event: (event[0], event[1]))
    return events


def _meta(meta_type: int, payload: bytes) -> bytes:
    return b"\xff" + bytes([meta_type]) + _vlq(len(payload)) + payload


def _track_chunk(body: bytes) -> bytes:
    return b"MTrk" + len(body).to_bytes(4, "big") + body


def _encode_track(events: list[tuple[int, int, int, int, int]], name: str) -> bytes:
    name_bytes = name[:127].encode("utf-8", "replace")
    body = bytearray()
    body += _vlq(0) + _meta(0x03, name_bytes)
    previous_tick = 0
    for tick, _order, status, data1, data2 in events:
        body += _vlq(tick - previous_tick) + bytes([status, data1, data2])
        previous_tick = tick
    body += _vlq(0) + _meta(0x2F, b"")
    return _track_chunk(bytes(body))


def _conductor_track(title: str, bpm: int) -> bytes:
    title_bytes = title[:127].encode("utf-8", "replace")
    tempo = round(60_000_000 / bpm)
    body = bytearray()
    body += _vlq(0) + _meta(0x03, title_bytes)
    body += _vlq(0) + _meta(0x51, tempo.to_bytes(3, "big"))
    body += _vlq(0) + _meta(0x58, bytes([4, 2, 24, 8]))  # 4/4
    body += _vlq(0) + _meta(0x2F, b"")
    return _track_chunk(bytes(body))


def _header(track_count: int) -> bytes:
    return (
        b"MThd"
        + (6).to_bytes(4, "big")
        + (1).to_bytes(2, "big")
        + track_count.to_bytes(2, "big")
        + PPQ.to_bytes(2, "big")
    )


def song_to_midi(draft: SongDraft) -> bytes:
    tracks = [_conductor_track(draft.title, draft.bpm)]
    ordered = sorted(draft.parts, key=lambda part: part.applyOrder)
    for index, part in enumerate(ordered):
        # channels 0-15 — correct for up to 16 parts; beyond that they wrap
        events = _note_events(part.payload.notes, index % 16)
        tracks.append(_encode_track(events, part.patternName))
    return _header(len(tracks)) + b"".join(tracks)


def payload_to_midi(payload: NotePayload) -> bytes:
    tracks = [
        _conductor_track(payload.title, payload.bpm),
        _encode_track(_note_events(payload.notes, 0), payload.title),
    ]
    return _header(len(tracks)) + b"".join(tracks)


def reconstruction_to_midi(project: ReconstructionProject) -> bytes:
    bpm = round(project.analysisSummary.bpm) if project.analysisSummary else 120
    tracks = [_conductor_track(project.title, bpm)]
    midi_parts = [part for part in project.parts if part.outputMode == "midi"]
    for index, part in enumerate(midi_parts):
        notes: list[Note] = []
        for pattern in part.patterns:
            for bar in pattern.placements:
                offset = (bar - 1) * 4
                for note in pattern.payload.notes:
                    notes.append(replace(note, startBeats=note.startBeats + offset))
        events = _note_events(notes, index % 16)
        tracks.append(_encode_track(events, part.name))
    return _header(len(tracks)) + b"".join(tracks)
