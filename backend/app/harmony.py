from __future__ import annotations

from dataclasses import dataclass

from .contracts import Note

_KNOWN_FAMILIES = {"amapiano", "afro", "hiphop"}

# Self-contained theory primitives (kept here so harmony stays a pure, independently
# testable module with no import cycle back into generator). NOTE: generator.py keeps
# its own ROOTS/_scale_notes; consolidating both into a shared theory module is a
# deferred minor.
_ROOTS = {
    "C": 48, "C#": 49, "Db": 49, "D": 50, "D#": 51, "Eb": 51,
    "E": 52, "F": 53, "F#": 54, "Gb": 54, "G": 55, "G#": 56,
    "Ab": 56, "A": 57, "A#": 58, "Bb": 58, "B": 59,
}
_MINOR = [0, 2, 3, 5, 7, 8, 10]
_MAJOR = [0, 2, 4, 5, 7, 9, 11]


@dataclass(frozen=True)
class GenreHarmony:
    progression: tuple[int, ...]  # diatonic scale degrees per bar (0 = tonic), cycles
    voicing: tuple[int, ...]      # diatonic stack offsets in scale STEPS from the chord root
    chord_octave: int             # semitone shift applied to the whole voicing (register)
    chord_sustain: float          # durationBeats of each sustained chord (must be <= 4)
    chord_velocity: float         # base velocity for chord notes
    chord_color: int              # FL piano-roll color for chords
    bass_octave: int              # semitone shift from the in-pool chord root to the bass root


GENRE_HARMONY: dict[str, GenreHarmony] = {
    "amapiano": GenreHarmony(
        progression=(0, 5, 2, 6),       # i - VI - III - VII
        voicing=(0, 2, 4, 6, 8),        # 9th pad (lush)
        chord_octave=0,
        chord_sustain=3.7,
        chord_velocity=0.42,
        chord_color=8,
        bass_octave=-12,
    ),
    "afro": GenreHarmony(
        progression=(0, 4, 5, 3),       # I - V - vi - IV
        voicing=(0, 2, 4, 8),           # triad + add9 (bright)
        chord_octave=12,
        chord_sustain=2.8,
        chord_velocity=0.5,
        chord_color=8,
        bass_octave=-12,
    ),
    "hiphop": GenreHarmony(
        progression=(1, 4, 0, 3),       # ii - v - i - iv
        voicing=(0, 2, 4, 6),           # diatonic 7th (jazzy)
        chord_octave=0,
        chord_sustain=2.5,
        chord_velocity=0.46,
        chord_color=8,
        bass_octave=-24,
    ),
}


def _validate_tables() -> None:
    if set(GENRE_HARMONY.keys()) != _KNOWN_FAMILIES:
        raise RuntimeError("GENRE_HARMONY families are out of sync with the generator")


_validate_tables()


def _scale_pool(key: str, scale: str) -> list[int]:
    root = _ROOTS.get(key, 57)
    intervals = _MAJOR if scale == "major" else _MINOR
    return [root + interval for interval in intervals]


def _degree_pitch(pool: list[int], degree: int) -> int:
    """Resolve a diatonic degree (may exceed the 7-note pool) to a MIDI pitch."""
    octaves, index = divmod(degree, len(pool))
    return pool[index] + 12 * octaves


def _harmony(family: str) -> GenreHarmony:
    harmony = GENRE_HARMONY.get(family)
    if harmony is None:
        raise ValueError(f"unknown harmony family: {family}")
    return harmony


def build_chords(family: str, key: str, scale: str, bars: int) -> list[Note]:
    harmony = _harmony(family)
    pool = _scale_pool(key, scale)
    notes: list[Note] = []
    for bar in range(bars):
        root_degree = harmony.progression[bar % len(harmony.progression)]
        start = bar * 4
        for offset in harmony.voicing:
            pitch = _degree_pitch(pool, root_degree + offset) + harmony.chord_octave
            notes.append(
                Note(
                    pitch=pitch,
                    startBeats=start,
                    durationBeats=harmony.chord_sustain,
                    velocity=harmony.chord_velocity,
                    color=harmony.chord_color,
                )
            )
    return notes


def chord_roots(family: str, key: str, scale: str, bars: int) -> list[int]:
    harmony = _harmony(family)
    pool = _scale_pool(key, scale)
    roots: list[int] = []
    for bar in range(bars):
        root_degree = harmony.progression[bar % len(harmony.progression)]
        roots.append(_degree_pitch(pool, root_degree) + harmony.bass_octave)
    return roots
