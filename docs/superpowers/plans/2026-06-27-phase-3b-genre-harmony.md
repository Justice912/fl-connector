# Phase 3b — Genre-specific Harmony Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give afro, hip-hop, and amapiano their own chord voicings and a bass that follows each genre's chord progression, so drafts sound like the genre they claim to be.

**Architecture:** A new pure module `backend/app/harmony.py` owns each genre's progression, chord voicings, and the per-bar bass root (`build_chords` + `chord_roots`, both deterministic). `backend/app/generator.py` keeps owning rhythm/arrangement and wires chords through `build_chords` and genre bass builders through `chord_roots`. The existing Phase 3a groove pass still wraps every part unchanged.

**Tech Stack:** Python 3.11 / pytest (backend venv at `backend/.venv`). Standard library only (`dataclasses`).

## Global Constraints

- Working dir: `C:\Users\HP\Vocals APP\fl-connector`. Branch: `phase-3b-genre-harmony` (already created, stacked on `phase-3a-swing-humanization`; spec committed at `691325d`).
- Backend test command: `cd backend && ./.venv/Scripts/python -m pytest -q`.
- This phase changes **pitches and note counts** of the chord and bass parts only. It does NOT touch drums, log-drum, or melody builders, and makes NO `Note`/`SongDraft` contract, request, or UI changes.
- Voicings use **diatonic stacking** — every chord tone is a member of the in-key scale (so chords never clash with the scale-based melody/log-drum).
- **Deterministic:** harmony is built from fixed constants (no randomness). The seeded groove pass still wraps output, so `generate_*` stays byte-identical across runs.
- Genre families are exactly `{"amapiano", "afro", "hiphop"}` (from `genre_family`). Harmony lookups raise `ValueError` on an unknown family.
- Contract bounds (from `app.contracts`): pitch `0–127`, velocity `0–1`, color `0–15`, `startBeats + durationBeats <= bars*4 + 0.001`.

**Spec:** `docs/superpowers/specs/2026-06-27-phase-3b-genre-harmony-design.md`

---

## Task 1: `harmony.py` module (`GenreHarmony` + `build_chords` + `chord_roots`)

**Files:**
- Create: `backend/app/harmony.py`
- Test: `backend/tests/test_harmony.py`

**Interfaces:**
- Produces:
  - `GenreHarmony(progression: tuple[int,...], voicing: tuple[int,...], chord_octave: int, chord_sustain: float, chord_velocity: float, chord_color: int, bass_octave: int)` (frozen dataclass).
  - `GENRE_HARMONY: dict[str, GenreHarmony]` keyed by `"amapiano"|"afro"|"hiphop"`.
  - `build_chords(family: str, key: str, scale: str, bars: int) -> list[Note]`.
  - `chord_roots(family: str, key: str, scale: str, bars: int) -> list[int]`.
- Consumes: `Note` from `app.contracts`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_harmony.py`:

```python
import pytest

from app.harmony import GENRE_HARMONY, build_chords, chord_roots

# A minor scale pitch classes: A(9) B(11) C(0) D(2) E(4) F(5) G(7)
_A_MINOR_PCS = {9, 11, 0, 2, 4, 5, 7}


def test_build_chords_is_in_key_and_in_range():
    for family in ("amapiano", "afro", "hiphop"):
        notes = build_chords(family, "A", "minor", bars=4)
        assert notes, family
        for note in notes:
            assert 0 <= note.pitch <= 127
            assert note.pitch % 12 in _A_MINOR_PCS, (family, note.pitch)
            note.validate()


def test_build_chords_count_matches_voicing_times_bars():
    for family, harmony in GENRE_HARMONY.items():
        notes = build_chords(family, "A", "minor", bars=4)
        assert len(notes) == 4 * len(harmony.voicing), family


def test_chord_roots_follow_progression_and_cycle():
    roots = chord_roots("hiphop", "A", "minor", bars=6)
    assert len(roots) == 6
    assert roots[0] == roots[4]   # progression cycles every 4 bars
    assert roots[1] == roots[5]
    assert roots[0] != roots[1]   # ii -> v is real harmonic movement


def test_genres_produce_distinct_chords():
    sets = {
        family: tuple(sorted(n.pitch for n in build_chords(family, "A", "minor", bars=4)))
        for family in ("amapiano", "afro", "hiphop")
    }
    assert sets["amapiano"] != sets["afro"]
    assert sets["amapiano"] != sets["hiphop"]
    assert sets["afro"] != sets["hiphop"]


def test_build_chords_is_deterministic():
    a = build_chords("amapiano", "A", "minor", bars=4)
    b = build_chords("amapiano", "A", "minor", bars=4)
    assert [n.to_dict() for n in a] == [n.to_dict() for n in b]


def test_chords_stay_within_bar_length():
    bars = 4
    for family in ("amapiano", "afro", "hiphop"):
        for note in build_chords(family, "A", "minor", bars=bars):
            assert note.startBeats + note.durationBeats <= bars * 4 + 0.001


def test_unknown_family_raises_and_zero_bars_empty():
    assert build_chords("amapiano", "A", "minor", bars=0) == []
    assert chord_roots("amapiano", "A", "minor", bars=0) == []
    with pytest.raises(ValueError):
        build_chords("nope", "A", "minor", bars=4)
    with pytest.raises(ValueError):
        chord_roots("nope", "A", "minor", bars=4)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_harmony.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.harmony'`.

- [ ] **Step 3: Implement `backend/app/harmony.py`**

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_harmony.py -q`
Expected: PASS (all 7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/harmony.py backend/tests/test_harmony.py
git commit -m "feat: add genre harmony module (voicings + progression roots)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Wire amapiano chords + progression-following bass

**Files:**
- Modify: `backend/app/generator.py`
- Test: `backend/tests/test_generator.py`

**Interfaces:**
- Consumes: `build_chords`, `chord_roots` (Task 1).
- Produces: refactored `_amapiano_bass(roots: list[int], bars: int) -> list[Note]`; `_generate_amapiano_song` and `_generate_amapiano_payload` now build chords via `build_chords("amapiano", ...)` and bass via `chord_roots("amapiano", ...)`.

> NOTE: `_amapiano_chords` is still referenced by `_generate_generic_song` after this task, so it stays defined here and is removed in Task 3.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_generator.py`:

```python
def test_amapiano_song_chords_use_extended_voicing():
    # amapiano 9th voicing = 5 sustained tones per bar; the chords role is never swung,
    # so each chord stays on its exact bar boundary.
    draft = generate_song_draft(prompt="deep amapiano song", genre="Amapiano", key="A", scale="minor", bars=4)
    chords = next(p for p in draft.parts if p.role == "chords")
    per_bar: dict[int, int] = {}
    for n in chords.payload.notes:
        per_bar[int(n.startBeats // 4)] = per_bar.get(int(n.startBeats // 4), 0) + 1
    assert per_bar and all(count == 5 for count in per_bar.values())


def test_amapiano_song_bass_follows_progression():
    # progression i-VI-III-VII is not constant, so the per-bar bass root must move.
    draft = generate_song_draft(prompt="deep amapiano song", genre="Amapiano", key="A", scale="minor", bars=4)
    bass = next(p for p in draft.parts if p.role == "bass")
    bar_min: dict[int, int] = {}
    for n in bass.payload.notes:
        bar = int(n.startBeats // 4)
        bar_min[bar] = min(bar_min.get(bar, 999), n.pitch)
    assert len(set(bar_min.values())) > 1, "bass should follow the progression, not stay on tonic"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_generator.py::test_amapiano_song_bass_follows_progression -q`
Expected: FAIL — today's `_amapiano_bass` is locked to the tonic root, so every bar's min pitch is identical and `set(bar_min.values())` has length 1.

- [ ] **Step 3: Import the harmony helpers**

In `backend/app/generator.py`, the existing groove import line is:

```python
from .groove import apply_groove, groove_seed
```

Add directly below it:

```python
from .harmony import build_chords, chord_roots
```

- [ ] **Step 4: Refactor `_amapiano_bass` to follow per-bar roots**

Replace the entire `_amapiano_bass` function:

```python
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
```

with:

```python
def _amapiano_bass(roots: list[int], bars: int) -> list[Note]:
    notes: list[Note] = []
    for bar in range(bars):
        base = bar * 4
        root = roots[bar]
        fifth = root + 7
        notes.append(Note(root, base, 0.72, 0.74, 5))
        notes.append(Note(root, base + 1.5, 0.42, 0.54, 5))
        notes.append(Note(fifth, base + 2.0, 0.62, 0.68, 5))
        notes.append(Note(root, base + 3.25, 0.42, 0.56, 5))
    return notes
```

- [ ] **Step 5: Wire the amapiano song chords + bass**

In `_generate_amapiano_song`, change the bass part's `notes=` from:

```python
                notes=_groove(_amapiano_bass(key, scale, bars), "bass", genre, key, bars, prompt),
```

to:

```python
                notes=_groove(_amapiano_bass(chord_roots("amapiano", key, scale, bars), bars), "bass", genre, key, bars, prompt),
```

And change the chords part's `notes=` from:

```python
                notes=_groove(_amapiano_chords(key, scale, bars), "chords", genre, key, bars, prompt),
```

to:

```python
                notes=_groove(build_chords("amapiano", key, scale, bars), "chords", genre, key, bars, prompt),
```

- [ ] **Step 6: Wire the amapiano payload chords + bass**

In `_generate_amapiano_payload`, replace the inline bass block:

```python
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
```

with (the per-bar root now follows the progression):

```python
    roots = chord_roots("amapiano", key, scale, bars)
    bass_offsets = [0.0, 2.0]
    for bar in range(bars):
        for offset in bass_offsets:
            notes.append(
                Note(
                    pitch=roots[bar],
                    startBeats=bar * 4 + offset,
                    durationBeats=0.62,
                    velocity=0.68,
                    color=5,
                )
            )
```

Then replace the conditional chord block:

```python
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
```

with:

```python
    if "chord" in prompt.lower() or "deep" in prompt.lower() or "hypnotic" in prompt.lower():
        notes.extend(build_chords("amapiano", key, scale, bars))
```

(Leave the `root`, `third`, `fifth`, `seventh`, `octave` locals — the log-drum block above still uses them.)

- [ ] **Step 7: Run the new tests + full suite**

Run: `cd backend && ./.venv/Scripts/python -m pytest -q`
Expected: PASS — the two new amapiano tests, plus all existing tests (they assert structure/colors/determinism/count-ranges, none of which break: amapiano chords go from 4→5 tones/bar but `sum(...) > 100` and `len(first)==len(second)` still hold; colors 2 and 5 still present).

If any pre-existing assertion fails because it pinned an exact pre-3b chord/bass pitch or count, update it to the new value and note it in the task report. (At plan-writing time, no such assertion exists.)

- [ ] **Step 8: Commit**

```bash
git add backend/app/generator.py backend/tests/test_generator.py
git commit -m "feat: amapiano chords + progression-following bass via harmony

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Genre chords + dedicated bass for afro & hip-hop

**Files:**
- Modify: `backend/app/generator.py`
- Test: `backend/tests/test_generator.py`

**Interfaces:**
- Consumes: `build_chords`, `chord_roots` (Task 1); `_FAMILY_MELODY` dispatch pattern (existing).
- Produces: `_afro_bass(roots, bars)`, `_hiphop_bass(roots, bars)`, `_FAMILY_BASS` dispatch map; `_generate_generic_song` builds chords via `build_chords(family, ...)` and bass via `_FAMILY_BASS[family](chord_roots(family, ...), bars)`. Removes the now-unused `_generic_bass` and `_amapiano_chords`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_generator.py`:

```python
def test_genres_have_distinct_chord_pitches():
    def chord_pitches(genre):
        draft = generate_song_draft(prompt=f"{genre} song", genre=genre, key="A", scale="minor", bars=4)
        chords = next(p for p in draft.parts if p.role == "chords")
        return tuple(sorted(n.pitch for n in chords.payload.notes))
    ama = chord_pitches("Amapiano")
    afro = chord_pitches("Afrobeats")
    hh = chord_pitches("Hip Hop")
    assert ama != afro
    assert ama != hh
    assert afro != hh


def test_afro_and_hiphop_bass_follow_progression():
    for genre in ("Afrobeats", "Hip Hop"):
        draft = generate_song_draft(prompt=f"{genre} song", genre=genre, key="A", scale="minor", bars=4)
        bass = next(p for p in draft.parts if p.role == "bass")
        bar_min: dict[int, int] = {}
        for n in bass.payload.notes:
            bar = int(n.startBeats // 4)
            bar_min[bar] = min(bar_min.get(bar, 999), n.pitch)
        assert len(set(bar_min.values())) > 1, f"{genre} bass should follow the progression"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_generator.py::test_genres_have_distinct_chord_pitches -q`
Expected: FAIL — afro/hip-hop still build chords with `_amapiano_chords`, so `ama == afro == hh` and the inequality assertions fail.

- [ ] **Step 3: Replace `_generic_bass` with genre bass builders**

Replace the entire `_generic_bass` function:

```python
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
```

with two genre-specific builders that follow the per-bar roots:

```python
def _afro_bass(roots: list[int], bars: int) -> list[Note]:
    # rolling syncopated 8th-bounce: root / octave / fifth, denser than the old shared bass
    notes: list[Note] = []
    for bar in range(bars):
        base = bar * 4
        root = roots[bar]
        octave = root + 12
        fifth = root + 7
        notes.append(Note(root, base + 0.0, 0.45, 0.74, 5))
        notes.append(Note(octave, base + 0.5, 0.3, 0.56, 5))
        notes.append(Note(fifth, base + 1.5, 0.4, 0.62, 5))
        notes.append(Note(root, base + 2.0, 0.45, 0.7, 5))
        notes.append(Note(octave, base + 2.5, 0.3, 0.54, 5))
        notes.append(Note(root, base + 3.25, 0.4, 0.6, 5))
    return notes


def _hiphop_bass(roots: list[int], bars: int) -> list[Note]:
    # sparse 808: long root on the downbeat, a pickup, and an octave pop; groove swings it
    notes: list[Note] = []
    for bar in range(bars):
        base = bar * 4
        root = roots[bar]
        octave = root + 12
        notes.append(Note(root, base + 0.0, 1.5, 0.8, 5))
        notes.append(Note(root, base + 2.5, 1.0, 0.66, 5))
        notes.append(Note(octave, base + 3.5, 0.4, 0.58, 5))
    return notes
```

- [ ] **Step 4: Remove the now-unused `_amapiano_chords`**

Delete the entire `_amapiano_chords` function (after Task 2 it is referenced only by `_generate_generic_song`, which Step 6 rewires):

```python
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
```

- [ ] **Step 5: Add the `_FAMILY_BASS` dispatch map and validate it**

Find the existing `_FAMILY_MELODY` definition:

```python
_FAMILY_MELODY = {"afro": _afro_melody, "hiphop": _hiphop_melody}
```

Add directly below it:

```python
_FAMILY_BASS = {"afro": _afro_bass, "hiphop": _hiphop_bass}
```

Then extend `_validate_family_tables` so its `table_keys` tuple includes the new map. Change:

```python
    table_keys = (
        _FAMILY_MELODY.keys(),
        _FAMILY_PATTERN_NAMES.keys(),
        _FAMILY_PLUGIN_HINTS.keys(),
    )
```

to:

```python
    table_keys = (
        _FAMILY_MELODY.keys(),
        _FAMILY_BASS.keys(),
        _FAMILY_PATTERN_NAMES.keys(),
        _FAMILY_PLUGIN_HINTS.keys(),
    )
```

- [ ] **Step 6: Wire `_generate_generic_song` chords + bass**

In `_generate_generic_song`, the `role_notes` dict currently reads:

```python
    role_notes = {
        "drums": _groove(_generic_drums(bars), "drums", genre, key, bars, prompt),
        "bass": _groove(_generic_bass(key, scale, bars), "bass", genre, key, bars, prompt),
        "chords": _groove(_amapiano_chords(key, scale, bars), "chords", genre, key, bars, prompt),
        "melody": _groove(melody_builder(key, scale, bars), "melody", genre, key, bars, prompt),
    }
```

Replace the `bass` and `chords` entries so it reads:

```python
    role_notes = {
        "drums": _groove(_generic_drums(bars), "drums", genre, key, bars, prompt),
        "bass": _groove(_FAMILY_BASS[family](chord_roots(family, key, scale, bars), bars), "bass", genre, key, bars, prompt),
        "chords": _groove(build_chords(family, key, scale, bars), "chords", genre, key, bars, prompt),
        "melody": _groove(melody_builder(key, scale, bars), "melody", genre, key, bars, prompt),
    }
```

- [ ] **Step 7: Run the new tests + full suite**

Run: `cd backend && ./.venv/Scripts/python -m pytest -q`
Expected: PASS — the two new genre-identity tests, plus all existing tests (afro/hip-hop drafts still have all four roles with non-empty notes; `_validate_family_tables` still passes because `_FAMILY_BASS` keys equal `_GENERIC_FAMILIES`).

If any pre-existing assertion fails because it pinned an exact pre-3b chord/bass pitch or count, update it and note it in the task report.

- [ ] **Step 8: Commit**

```bash
git add backend/app/generator.py backend/tests/test_generator.py
git commit -m "feat: genre-specific chords + bass for afro and hip-hop

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- New pure `harmony.py` (`GenreHarmony` + `GENRE_HARMONY` + `build_chords` + `chord_roots`) → Task 1. Diatonic stacking, per-genre register/sustain/velocity → Task 1 tables + `_degree_pitch`. `ValueError` on unknown family, import-time table guard → Task 1. Per-genre progressions (amapiano i-VI-III-VII, afro I-V-vi-IV, boom-bap ii-v-i-iv) → Task 1 `GENRE_HARMONY`. Bass follows the progression via the shared `chord_roots` source of truth → Tasks 2 (amapiano) + 3 (afro/hiphop). Genre bass rhythms (amapiano sub-pulse, afro rolling bounce, hiphop sparse 808) → Tasks 2/3. `_generic_bass` removed; afro/hiphop get dedicated builders → Task 3. Amapiano refined (ad-hoc 4 shapes → coherent loop) → Task 2 via `build_chords`. Chord rhythm stays sustained, drums/log-drum/melody untouched, no contract/request/UI changes → respected (only `generator.py` chord/bass wiring + new `harmony.py`). Determinism (fixed constants; groove still wraps) → Task 1 determinism test + existing determinism tests stay green. Genre distinctness + in-key + pitch-range + boundary → Task 1 tests; integration distinctness + bass-follows-progression → Tasks 2/3 tests. Afro/hiphop single-pattern payload builders stay melody-only → untouched (not in any task). All spec sections covered.

**Placeholder scan:** No TBD/TODO; every code step shows the complete before/after code.

**Type consistency:** `build_chords(family, key, scale, bars) -> list[Note]` and `chord_roots(family, key, scale, bars) -> list[int]` are defined in Task 1 and called identically in Tasks 2–3. `_amapiano_bass`/`_afro_bass`/`_hiphop_bass` all share the `(roots: list[int], bars: int) -> list[Note]` signature; `_FAMILY_BASS` maps families to those builders and is fed `chord_roots(family, ...)`. `GenreHarmony` field names (`progression`, `voicing`, `chord_octave`, `chord_sustain`, `chord_velocity`, `chord_color`, `bass_octave`) are used consistently in the tables and both functions. Families are the same `{"amapiano","afro","hiphop"}` set in `harmony._KNOWN_FAMILIES`, the generator's `genre_family`, and `_GENERIC_FAMILIES`.

**Ordering note:** `_amapiano_chords` is removed only in Task 3 (Step 4) — after Task 2 it is still referenced by `_generate_generic_song`, so removing it earlier would break that path.
