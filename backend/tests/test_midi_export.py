from app.generator import generate_payload, generate_song_draft
from app.midi_export import payload_to_midi, song_to_midi


def _read_vlq(data: bytes, index: int) -> tuple[int, int]:
    value = 0
    while True:
        byte = data[index]
        index += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, index


def _parse_track(body: bytes) -> dict:
    index = 0
    abs_tick = 0
    name = None
    tempo = None
    notes: list[tuple[int, int, int, int]] = []
    while index < len(body):
        delta, index = _read_vlq(body, index)
        abs_tick += delta
        status = body[index]
        index += 1
        if status == 0xFF:
            meta = body[index]
            index += 1
            length, index = _read_vlq(body, index)
            chunk = body[index : index + length]
            index += length
            if meta == 0x03:
                name = chunk.decode("utf-8")
            elif meta == 0x51:
                tempo = int.from_bytes(chunk, "big")
            elif meta == 0x2F:
                break
        elif status & 0xF0 in (0x80, 0x90):
            pitch = body[index]
            velocity = body[index + 1]
            index += 2
            if status & 0xF0 == 0x90 and velocity > 0:
                notes.append((abs_tick, pitch, velocity, status & 0x0F))
        else:  # pragma: no cover - writer never emits other channel events
            index += 2
    return {"name": name, "tempo": tempo, "notes": notes}


def parse_midi(data: bytes) -> dict:
    assert data[:4] == b"MThd"
    fmt = int.from_bytes(data[8:10], "big")
    ntrks = int.from_bytes(data[10:12], "big")
    division = int.from_bytes(data[12:14], "big")
    tracks = []
    index = 14
    for _ in range(ntrks):
        assert data[index : index + 4] == b"MTrk"
        length = int.from_bytes(data[index + 4 : index + 8], "big")
        body = data[index + 8 : index + 8 + length]
        index += 8 + length
        tracks.append(_parse_track(body))
    return {"format": fmt, "ntrks": ntrks, "division": division, "tracks": tracks}


def test_song_to_midi_has_track_per_part_tempo_and_notes():
    draft = generate_song_draft(
        prompt="deep amapiano song", genre="Amapiano", bpm=120, key="A", scale="minor", bars=4
    )
    parsed = parse_midi(song_to_midi(draft))

    assert parsed["format"] == 1
    assert parsed["division"] == 96
    assert parsed["ntrks"] == len(draft.parts) + 1
    assert parsed["tracks"][0]["tempo"] == round(60_000_000 / 120)

    ordered = sorted(draft.parts, key=lambda part: part.applyOrder)
    assert [track["name"] for track in parsed["tracks"][1:]] == [part.patternName for part in ordered]

    total_src = sum(len(part.payload.notes) for part in draft.parts)
    total_mid = sum(len(track["notes"]) for track in parsed["tracks"][1:])
    assert total_mid == total_src


def test_payload_to_midi_round_trips_notes_and_ticks():
    payload = generate_payload(prompt="amapiano log drum", genre="Amapiano", key="C", bpm=110, bars=2)
    parsed = parse_midi(payload_to_midi(payload))

    assert parsed["ntrks"] == 2
    assert len(parsed["tracks"][1]["notes"]) == len(payload.notes)

    lowest_start = min(note.startBeats for note in payload.notes)
    ticks = sorted(note[0] for note in parsed["tracks"][1]["notes"])
    assert ticks[0] == round(lowest_start * 96)


def test_muted_notes_are_excluded():
    from app.contracts import Note
    from app.midi_export import _note_events

    live = Note(60, 0.0, 1.0, 0.8)
    muted = Note(62, 0.0, 1.0, 0.8, muted=True)
    pitches = {event[3] for event in _note_events([live, muted], 0)}
    assert 60 in pitches
    assert 62 not in pitches
