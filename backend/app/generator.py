from __future__ import annotations

import re

from .contracts import ArrangementSection, Note, NotePayload, SongDraft, SongPart

ROOTS = {
    "C": 48,
    "C#": 49,
    "Db": 49,
    "D": 50,
    "D#": 51,
    "Eb": 51,
    "E": 52,
    "F": 53,
    "F#": 54,
    "Gb": 54,
    "G": 55,
    "G#": 56,
    "Ab": 56,
    "A": 57,
    "A#": 58,
    "Bb": 58,
    "B": 59,
}

MINOR_SCALE = [0, 2, 3, 5, 7, 8, 10, 12]
MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11, 12]


def normalize_key(key: str) -> str:
    match = re.match(r"^([A-G](?:#|b)?)(?:\s*(major|minor|maj|min|m))?$", key.strip(), re.I)
    if not match:
        return "A"
    root = match.group(1)
    return root[0].upper() + root[1:]


def infer_scale(prompt: str, requested: str) -> str:
    lowered = prompt.lower()
    if "major" in lowered:
        return "major"
    if "minor" in lowered or "dark" in lowered or "deep" in lowered:
        return "minor"
    return requested if requested in {"major", "minor"} else "minor"


def infer_title(prompt: str, genre: str) -> str:
    if "log drum" in prompt.lower():
        return f"{genre} log drum riff"
    if "bass" in prompt.lower():
        return f"{genre} bass phrase"
    if "chord" in prompt.lower():
        return f"{genre} chord sketch"
    return f"{genre} note draft"


def genre_family(genre: str) -> str:
    lowered = genre.strip().lower()
    if "amapiano" in lowered:
        return "amapiano"
    if "afro" in lowered:
        return "afro"
    if "hip" in lowered or "trap" in lowered:
        return "hiphop"
    return "amapiano"


def generate_payload(
    *,
    prompt: str,
    genre: str = "Amapiano",
    bpm: int = 113,
    key: str = "A",
    scale: str = "minor",
    bars: int = 4,
) -> NotePayload:
    key = normalize_key(key)
    scale = infer_scale(prompt, scale)
    family = genre_family(genre)
    if family == "afro":
        return _generate_afro_payload(prompt, genre, bpm, key, scale, bars)
    if family == "hiphop":
        return _generate_hiphop_payload(prompt, genre, bpm, key, scale, bars)
    return _generate_amapiano_payload(prompt, genre, bpm, key, scale, bars)


def generate_song_draft(
    *,
    prompt: str,
    genre: str = "Amapiano",
    bpm: int = 113,
    key: str = "A",
    scale: str = "minor",
    bars: int = 8,
) -> SongDraft:
    key = normalize_key(key)
    scale = infer_scale(prompt, scale)
    family = genre_family(genre)
    if family == "amapiano":
        return _generate_amapiano_song(prompt, genre, bpm, key, scale, bars)
    return _generate_generic_song(family, prompt, genre, bpm, key, scale, bars)


def _scale_notes(key: str, scale: str) -> list[int]:
    root = ROOTS.get(key, 57)
    intervals = MAJOR_SCALE if scale == "major" else MINOR_SCALE
    return [root + interval for interval in intervals]


def _payload(
    *,
    title: str,
    prompt: str,
    genre: str,
    bpm: int,
    key: str,
    scale: str,
    bars: int,
    notes: list[Note],
) -> NotePayload:
    return NotePayload.create(
        title=title,
        sourcePrompt=prompt,
        genre=genre,
        bpm=bpm,
        key=key,
        scale=scale,
        bars=bars,
        notes=sorted(notes, key=lambda note: (note.startBeats, note.pitch)),
    )


def _generate_amapiano_song(
    prompt: str,
    genre: str,
    bpm: int,
    key: str,
    scale: str,
    bars: int,
) -> SongDraft:
    parts = [
        SongPart.create(
            role="drums",
            patternName="FPC bounce drums",
            pluginHint="FPC - route kick, clap, closed hat, open hat, and shaker pads",
            applyOrder=1,
            payload=_payload(
                title="FPC bounce drums",
                prompt=f"{prompt} | drums",
                genre=genre,
                bpm=bpm,
                key=key,
                scale=scale,
                bars=bars,
                notes=_amapiano_drums(bars),
            ),
        ),
        SongPart.create(
            role="bass",
            patternName="Deep sub bass pulse",
            pluginHint="3xOsc sine sub or BooBass - keep centered and simple",
            applyOrder=2,
            payload=_payload(
                title="Deep sub bass pulse",
                prompt=f"{prompt} | bass",
                genre=genre,
                bpm=bpm,
                key=key,
                scale=scale,
                bars=bars,
                notes=_amapiano_bass(key, scale, bars),
            ),
        ),
        SongPart.create(
            role="chords",
            patternName="FLEX warm pad chords",
            pluginHint="FLEX - Pads category, wide reverb after routing to Mixer",
            applyOrder=3,
            payload=_payload(
                title="FLEX warm pad chords",
                prompt=f"{prompt} | chords",
                genre=genre,
                bpm=bpm,
                key=key,
                scale=scale,
                bars=bars,
                notes=_amapiano_chords(key, scale, bars),
            ),
        ),
        SongPart.create(
            role="log_drum",
            patternName="Main log drum riff",
            pluginHint="FPC tuned percussion or FLEX mallet/log-style preset",
            applyOrder=4,
            payload=_payload(
                title="Main log drum riff",
                prompt=f"{prompt} | log drum",
                genre=genre,
                bpm=bpm,
                key=key,
                scale=scale,
                bars=bars,
                notes=_amapiano_log_drum(key, scale, bars),
            ),
        ),
        SongPart.create(
            role="melody",
            patternName="Sparse top response",
            pluginHint="FLEX - soft bell, pluck, or keys preset",
            applyOrder=5,
            payload=_payload(
                title="Sparse top response",
                prompt=f"{prompt} | melody",
                genre=genre,
                bpm=bpm,
                key=key,
                scale=scale,
                bars=bars,
                notes=_amapiano_melody(key, scale, bars),
            ),
        ),
    ]

    return SongDraft.create(
        title=f"{genre} full draft",
        sourcePrompt=prompt,
        genre=genre,
        bpm=bpm,
        key=key,
        scale=scale,
        bars=bars,
        parts=parts,
        arrangement=_arrangement(bars),
    )


def _amapiano_drums(bars: int) -> list[Note]:
    notes: list[Note] = []
    for bar in range(bars):
        base = bar * 4
        for offset in [0.0, 2.0]:
            notes.append(Note(36, base + offset, 0.18, 0.88, 5))
        for offset in [1.0, 3.0]:
            notes.append(Note(39, base + offset, 0.14, 0.68, 3))
        for step in range(8):
            velocity = 0.46 if step % 2 else 0.58
            notes.append(Note(42, base + step * 0.5, 0.1, velocity, 2))
        for offset in [1.75, 3.5]:
            notes.append(Note(46, base + offset, 0.18, 0.52, 4))
        for step in range(16):
            if step not in {0, 8}:
                notes.append(Note(70, base + step * 0.25, 0.08, 0.34, 6))
    return notes


def _amapiano_bass(key: str, scale: str, bars: int) -> list[Note]:
    pool = _scale_notes(key, scale)
    root = pool[0] - 12
    fifth = pool[4] - 12
    notes: list[Note] = []
    for bar in range(bars):
        base = bar * 4
        notes.append(Note(root, base, 0.72, 0.74, 5))
        notes.append(Note(root, base + 1.5, 0.42, 0.54, 5))
        notes.append(Note(fifth, base + 2.0, 0.62, 0.68, 5))
        notes.append(Note(root, base + 3.25, 0.42, 0.56, 5))
    return notes


def _amapiano_chords(key: str, scale: str, bars: int) -> list[Note]:
    pool = _scale_notes(key, scale)
    root, third, fifth, seventh = pool[0], pool[2], pool[4], pool[6]
    chord_shapes = [
        [root, third, fifth, seventh],
        [pool[5] - 12, root, third, fifth],
        [fifth - 12, seventh, pool[1] + 12, pool[4]],
        [pool[3] - 12, seventh, root + 12, third + 12],
    ]
    notes: list[Note] = []
    for bar in range(bars):
        for pitch in chord_shapes[bar % len(chord_shapes)]:
            notes.append(Note(pitch, bar * 4, 3.65, 0.42, 8))
    return notes


def _amapiano_log_drum(key: str, scale: str, bars: int) -> list[Note]:
    pool = _scale_notes(key, scale)
    root, third, fifth, seventh, octave = pool[0], pool[2], pool[4], pool[6], pool[7]
    offsets = [0.0, 0.75, 1.5, 2.25, 2.75, 3.5]
    pitches = [root + 12, fifth + 12, third + 12, seventh + 12, fifth + 12, octave + 12]
    notes: list[Note] = []
    for bar in range(bars):
        for index, offset in enumerate(offsets):
            notes.append(
                Note(
                    pitches[(index + bar) % len(pitches)],
                    bar * 4 + offset,
                    0.32,
                    0.72 + (0.12 if index in {0, 3} else 0),
                    2,
                )
            )
    return notes


def _amapiano_melody(key: str, scale: str, bars: int) -> list[Note]:
    pool = _scale_notes(key, scale)
    motif = [(0.5, pool[4] + 12), (1.25, pool[6] + 12), (2.5, pool[7] + 12), (3.25, pool[2] + 24)]
    notes: list[Note] = []
    for bar in range(bars):
        if bar % 2 == 0:
            for offset, pitch in motif:
                notes.append(Note(pitch, bar * 4 + offset, 0.38, 0.48, 7))
    return notes


def _arrangement(
    bars: int,
    roles: tuple[str, ...] | list[str] = ("drums", "bass", "chords", "log_drum", "melody"),
) -> list[ArrangementSection]:
    available = set(roles)
    if bars >= 16:
        lengths = [4, 4, 4, bars - 12]
    elif bars >= 8:
        lengths = [2, 2, 2, bars - 6]
    else:
        lengths = [1, 1, 1, max(1, bars - 3)]
    starts = [1]
    for length in lengths[:-1]:
        starts.append(starts[-1] + length)
    plan = [
        ("Intro", ["chords", "drums"]),
        ("Groove", ["drums", "bass", "chords"]),
        ("Drop", ["drums", "bass", "chords", "log_drum"]),
        ("Hook", ["drums", "bass", "chords", "log_drum", "melody"]),
    ]
    sections: list[ArrangementSection] = []
    for index, (name, parts) in enumerate(plan):
        active = [part for part in parts if part in available] or sorted(available)
        sections.append(ArrangementSection(name, starts[index], lengths[index], active))
    return sections


def _generate_amapiano_payload(
    prompt: str,
    genre: str,
    bpm: int,
    key: str,
    scale: str,
    bars: int,
) -> NotePayload:
    pool = _scale_notes(key, scale)
    root = pool[0]
    third = pool[2]
    fifth = pool[4]
    seventh = pool[6]
    octave = pool[7]
    notes: list[Note] = []

    log_offsets = [0.0, 0.75, 1.5, 2.25, 2.75, 3.5]
    log_pitches = [root + 12, fifth + 12, third + 12, seventh + 12, fifth + 12, octave + 12]
    for bar in range(bars):
        base = bar * 4
        for index, offset in enumerate(log_offsets):
            pitch = log_pitches[(index + bar) % len(log_pitches)]
            velocity = 0.72 + (0.12 if index in {0, 3} else 0.0)
            notes.append(
                Note(
                    pitch=pitch,
                    startBeats=base + offset,
                    durationBeats=0.32,
                    velocity=velocity,
                    color=2,
                )
            )

    bass_offsets = [0.0, 2.0]
    for bar in range(bars):
        for offset in bass_offsets:
            notes.append(
                Note(
                    pitch=root - 12,
                    startBeats=bar * 4 + offset,
                    durationBeats=0.62,
                    velocity=0.68,
                    color=5,
                )
            )

    if "chord" in prompt.lower() or "deep" in prompt.lower() or "hypnotic" in prompt.lower():
        chord_tones = [root, third, fifth, seventh]
        for bar in range(bars):
            for pitch in chord_tones:
                notes.append(
                    Note(
                        pitch=pitch,
                        startBeats=bar * 4,
                        durationBeats=3.75,
                        velocity=0.44,
                        color=8,
                    )
                )

    return _payload(
        title=infer_title(prompt, genre),
        prompt=prompt,
        genre=genre,
        bpm=bpm,
        key=key,
        scale=scale,
        bars=bars,
        notes=notes,
    )


def _afro_melody(key: str, scale: str, bars: int) -> list[Note]:
    pool = _scale_notes(key, scale)
    root = pool[0]
    motif = [(0.0, 7), (0.5, 9), (1.25, 4), (1.75, 7), (2.5, 2), (3.25, 4)]
    return [
        Note(root + degree + 12, bar * 4 + offset, 0.42, 0.74, 3)
        for bar in range(bars)
        for offset, degree in motif
    ]


def _hiphop_melody(key: str, scale: str, bars: int) -> list[Note]:
    pool = _scale_notes(key, scale)
    root = pool[0]
    motif = [(0.0, 0), (0.75, 3), (1.5, 7), (2.5, 10), (3.0, 7)]
    return [
        Note(root + interval + 12, bar * 4 + offset, 0.5, 0.72, 4)
        for bar in range(bars)
        for offset, interval in motif
    ]


def _generic_drums(bars: int) -> list[Note]:
    notes: list[Note] = []
    for bar in range(bars):
        base = bar * 4
        for beat in range(4):
            notes.append(Note(36, base + beat, 0.2, 0.9, 5))
        for beat in (1, 3):
            notes.append(Note(39, base + beat, 0.16, 0.7, 3))
        for step in range(8):
            notes.append(Note(42, base + step * 0.5, 0.1, 0.5 if step % 2 else 0.6, 2))
    return notes


def _generic_bass(key: str, scale: str, bars: int) -> list[Note]:
    pool = _scale_notes(key, scale)
    root = pool[0] - 12
    fifth = pool[4] - 12
    notes: list[Note] = []
    for bar in range(bars):
        base = bar * 4
        notes.append(Note(root, base, 0.9, 0.74, 5))
        notes.append(Note(root, base + 1.5, 0.5, 0.6, 5))
        notes.append(Note(fifth, base + 2.5, 0.5, 0.64, 5))
        notes.append(Note(root, base + 3.5, 0.4, 0.56, 5))
    return notes


_FAMILY_MELODY = {"afro": _afro_melody, "hiphop": _hiphop_melody}
_FAMILY_PATTERN_NAMES = {
    "afro": {
        "drums": "Afrobeats kit groove",
        "bass": "Rolling afro bass",
        "chords": "Chord progression",
        "melody": "Afro lead motif",
    },
    "hiphop": {
        "drums": "Boom-bap kit",
        "bass": "808 sub bass",
        "chords": "Chord progression",
        "melody": "Hip-hop lead hook",
    },
}
_FAMILY_PLUGIN_HINTS = {
    "afro": {
        "drums": "FPC - afro kit",
        "bass": "3xOsc or FLEX bass, keep centered",
        "chords": "FLEX keys or pad",
        "melody": "FLEX pluck or marimba preset",
    },
    "hiphop": {
        "drums": "FPC - boom-bap kit",
        "bass": "3xOsc 808 sub",
        "chords": "FLEX keys or sampler stab",
        "melody": "FLEX lead preset",
    },
}

_GENERIC_FAMILIES = {"afro", "hiphop"}
_GENERIC_ROLES = {"drums", "bass", "chords", "melody"}
assert _GENERIC_FAMILIES == _FAMILY_MELODY.keys() == _FAMILY_PATTERN_NAMES.keys() == _FAMILY_PLUGIN_HINTS.keys()
for _family in _GENERIC_FAMILIES:
    assert _GENERIC_ROLES <= _FAMILY_PATTERN_NAMES[_family].keys()
    assert _GENERIC_ROLES <= _FAMILY_PLUGIN_HINTS[_family].keys()


def _generate_afro_payload(
    prompt: str, genre: str, bpm: int, key: str, scale: str, bars: int
) -> NotePayload:
    return _payload(
        title=infer_title(prompt, genre),
        prompt=prompt,
        genre=genre,
        bpm=bpm,
        key=key,
        scale=scale,
        bars=bars,
        notes=_afro_melody(key, scale, bars),
    )


def _generate_hiphop_payload(
    prompt: str, genre: str, bpm: int, key: str, scale: str, bars: int
) -> NotePayload:
    return _payload(
        title=infer_title(prompt, genre),
        prompt=prompt,
        genre=genre,
        bpm=bpm,
        key=key,
        scale=scale,
        bars=bars,
        notes=_hiphop_melody(key, scale, bars),
    )


def _generate_generic_song(
    family: str, prompt: str, genre: str, bpm: int, key: str, scale: str, bars: int
) -> SongDraft:
    names = _FAMILY_PATTERN_NAMES[family]
    hints = _FAMILY_PLUGIN_HINTS[family]
    melody_builder = _FAMILY_MELODY[family]
    role_notes = {
        "drums": _generic_drums(bars),
        "bass": _generic_bass(key, scale, bars),
        "chords": _amapiano_chords(key, scale, bars),
        "melody": melody_builder(key, scale, bars),
    }
    roles = ["drums", "bass", "chords", "melody"]
    parts = [
        SongPart.create(
            role=role,
            patternName=names[role],
            pluginHint=hints[role],
            applyOrder=index + 1,
            payload=_payload(
                title=names[role],
                prompt=f"{prompt} | {role}",
                genre=genre,
                bpm=bpm,
                key=key,
                scale=scale,
                bars=bars,
                notes=role_notes[role],
            ),
        )
        for index, role in enumerate(roles)
    ]
    return SongDraft.create(
        title=f"{genre} full draft",
        sourcePrompt=prompt,
        genre=genre,
        bpm=bpm,
        key=key,
        scale=scale,
        bars=bars,
        parts=parts,
        arrangement=_arrangement(bars, roles),
    )
