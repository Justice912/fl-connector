# Phase 3c — Genre-specific Drum Fills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Break the static drum loop by adding a deterministic, genre-specific fill on the last beat of each 4-bar phrase (plus the final bar) of every song draft's drums part.

**Architecture:** A new pure module `backend/app/fills.py` owns per-genre fill templates and `apply_fills(notes, *, family, bars)`, which drops the base drum hits in the last beat of each fill bar and inserts the genre fill. `backend/app/generator.py` calls it on the drums note list *before* the existing groove pass, at both song-assembly points. The Phase 3a groove pass and 3b harmony are unchanged.

**Tech Stack:** Python 3.11 / pytest (backend venv at `backend/.venv`). Standard library only.

## Global Constraints

- Working dir: `C:\Users\HP\Vocals APP\fl-connector`. Branch: `phase-3c-drum-fills` (already created, stacked on `phase-3b-genre-harmony`; spec committed).
- Backend test command (from `backend`): `./.venv/Scripts/python -m pytest -q`.
- This phase changes ONLY the **drums** part of song drafts. It does NOT touch bass, chords, log-drum, or melody builders; does NOT change the single-pattern payloads; makes NO `Note`/`SongDraft` contract, request, or UI changes.
- Fills use ONLY each genre's existing kit pitches: kick 36 (color 5), snare/clap 39 (color 3), closed hat 42 (color 2), open hat 46 (color 4), shaker 70 (color 6).
- **Deterministic:** fixed templates, no randomness. The seeded groove pass still wraps the drums, so `generate_song_draft` stays byte-identical across runs.
- Fill window is the last beat `[3.0, 4.0)`; every fill note has `offset + duration <= 4.0`.
- Fill bars (0-indexed) = `{bar for bar in range(bars) if (bar+1) % 4 == 0}` plus `bars - 1`.
- Genre families are exactly `{"amapiano","afro","hiphop"}`; `apply_fills` raises `ValueError` on an unknown family.
- Contract bounds (`app.contracts`): pitch 0–127, velocity 0–1, color 0–15, `startBeats + durationBeats <= bars*4 + 0.001`.

**Spec:** `docs/superpowers/specs/2026-06-27-phase-3c-drum-fills-design.md`

---

## Task 1: `fills.py` module (templates + `apply_fills`)

**Files:**
- Create: `backend/app/fills.py`
- Test: `backend/tests/test_fills.py`

**Interfaces:**
- Produces:
  - `FILL_WINDOW_START: float` (3.0), `FillNote` type alias, `FILL_TEMPLATES: dict[str, tuple[FillNote, ...]]` keyed by `"amapiano"|"afro"|"hiphop"`.
  - `apply_fills(notes: list[Note], *, family: str, bars: int) -> list[Note]`.
- Consumes: `Note` from `app.contracts`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_fills.py`:

```python
import pytest

from app.contracts import Note
from app.fills import FILL_TEMPLATES, apply_fills


def _steady_drums(bars):
    # kick on beat 0 (outside the fill window) + a unique marker hit (pitch 99) in the
    # last-beat window [3.0,4.0) of every bar, so removal is unambiguous.
    notes = []
    for bar in range(bars):
        base = bar * 4
        notes.append(Note(36, base + 0.0, 0.2, 0.9, 5))
        notes.append(Note(99, base + 3.5, 0.1, 0.5, 2))
    return notes


def test_fill_bars_selected_for_various_lengths():
    # amapiano fill introduces shaker pitch 70, which the base pattern never uses,
    # so pitch-70 bars mark exactly the filled bars.
    def filled_bars(bars):
        out = apply_fills(_steady_drums(bars), family="amapiano", bars=bars)
        return sorted({int(n.startBeats // 4) for n in out if n.pitch == 70})
    assert filled_bars(4) == [3]
    assert filled_bars(8) == [3, 7]
    assert filled_bars(2) == [1]   # final-bar rule when no full phrase boundary


def test_window_base_hits_removed_only_on_fill_bars():
    out = apply_fills(_steady_drums(8), family="afro", bars=8)
    # the marker (99) in the window survives on non-fill bars, is removed on fill bars 3 & 7
    assert sorted({int(n.startBeats // 4) for n in out if n.pitch == 99}) == [0, 1, 2, 4, 5, 6]
    # the beat-0 kick (outside the window) survives on every bar, incl. fill bar 3 (start 12.0)
    assert any(n.pitch == 36 and abs(n.startBeats - 12.0) < 1e-9 for n in out)


def test_non_fill_bars_are_byte_identical_to_input():
    base = _steady_drums(8)
    out = apply_fills(base, family="amapiano", bars=8)
    base_non_fill = [n.to_dict() for n in base if int(n.startBeats // 4) not in {3, 7}]
    out_non_fill = [n.to_dict() for n in out if int(n.startBeats // 4) not in {3, 7}]
    assert out_non_fill == base_non_fill


def test_genres_produce_distinct_fills():
    base = _steady_drums(4)
    sets = {
        fam: tuple(sorted((n.pitch, n.startBeats, n.velocity) for n in apply_fills(base, family=fam, bars=4)))
        for fam in ("amapiano", "afro", "hiphop")
    }
    assert sets["amapiano"] != sets["afro"]
    assert sets["amapiano"] != sets["hiphop"]
    assert sets["afro"] != sets["hiphop"]


def test_deterministic_and_input_not_mutated():
    base = _steady_drums(8)
    snapshot = [n.to_dict() for n in base]
    a = apply_fills(base, family="hiphop", bars=8)
    b = apply_fills(base, family="hiphop", bars=8)
    assert [n.to_dict() for n in a] == [n.to_dict() for n in b]
    assert [n.to_dict() for n in base] == snapshot  # input list untouched


def test_fill_notes_valid_and_within_bar():
    out = apply_fills(_steady_drums(8), family="amapiano", bars=8)
    for n in out:
        n.validate()
        bar = int(n.startBeats // 4)
        assert n.startBeats + n.durationBeats <= bar * 4 + 4.0 + 1e-9


def test_unknown_family_raises_and_empty_returns_empty():
    assert apply_fills([], family="amapiano", bars=4) == []
    with pytest.raises(ValueError):
        apply_fills(_steady_drums(4), family="nope", bars=4)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_fills.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.fills'`.

- [ ] **Step 3: Implement `backend/app/fills.py`**

```python
from __future__ import annotations

from .contracts import Note

_KNOWN_FAMILIES = {"amapiano", "afro", "hiphop"}

FILL_WINDOW_START = 3.0  # the fill occupies the last beat [3.0, 4.0) of a fill bar

# (pitch, offset_in_bar, durationBeats, velocity, color)
FillNote = tuple[int, float, float, float, int]

FILL_TEMPLATES: dict[str, tuple[FillNote, ...]] = {
    "amapiano": (
        (42, 3.0, 0.1, 0.50, 2),
        (42, 3.25, 0.1, 0.62, 2),
        (42, 3.5, 0.1, 0.74, 2),
        (42, 3.75, 0.1, 0.88, 2),
        (70, 3.0, 0.06, 0.30, 6),
        (70, 3.125, 0.06, 0.34, 6),
        (70, 3.25, 0.06, 0.39, 6),
        (70, 3.375, 0.06, 0.43, 6),
        (70, 3.5, 0.06, 0.48, 6),
        (70, 3.625, 0.06, 0.53, 6),
        (70, 3.75, 0.06, 0.57, 6),
        (70, 3.875, 0.06, 0.62, 6),
        (46, 3.75, 0.18, 0.60, 4),
    ),
    "afro": (
        (36, 3.0, 0.18, 0.85, 5),
        (36, 3.5, 0.18, 0.80, 5),
        (39, 3.25, 0.14, 0.50, 3),
        (39, 3.75, 0.14, 0.82, 3),
        (42, 3.0, 0.1, 0.50, 2),
        (42, 3.25, 0.1, 0.50, 2),
        (42, 3.5, 0.1, 0.50, 2),
        (42, 3.75, 0.1, 0.50, 2),
    ),
    "hiphop": (
        (39, 3.0, 0.08, 0.40, 3),
        (39, 3.125, 0.08, 0.47, 3),
        (39, 3.25, 0.08, 0.54, 3),
        (39, 3.375, 0.08, 0.61, 3),
        (39, 3.5, 0.08, 0.69, 3),
        (39, 3.625, 0.08, 0.76, 3),
        (39, 3.75, 0.08, 0.83, 3),
        (39, 3.875, 0.08, 0.90, 3),
    ),
}


def _validate_tables() -> None:
    if set(FILL_TEMPLATES.keys()) != _KNOWN_FAMILIES:
        raise RuntimeError("FILL_TEMPLATES families are out of sync with the generator")
    for family, template in FILL_TEMPLATES.items():
        for _pitch, offset, duration, _velocity, _color in template:
            if not FILL_WINDOW_START <= offset < 4.0:
                raise RuntimeError(f"{family} fill offset {offset} is outside the fill window")
            if offset + duration > 4.0:
                raise RuntimeError(f"{family} fill note at offset {offset} exceeds the bar")


_validate_tables()


def _fill_bars(bars: int) -> set[int]:
    if bars <= 0:
        return set()
    fill_bars = {bar for bar in range(bars) if (bar + 1) % 4 == 0}
    fill_bars.add(bars - 1)
    return fill_bars


def apply_fills(notes: list[Note], *, family: str, bars: int) -> list[Note]:
    if family not in FILL_TEMPLATES:
        raise ValueError(f"unknown fill family: {family}")
    if not notes:
        return []
    template = FILL_TEMPLATES[family]
    fill_bars = _fill_bars(bars)
    result: list[Note] = []
    # 1) keep every base note except the last-beat hits of fill bars
    for note in notes:
        bar = int(note.startBeats // 4)
        window_start = bar * 4 + FILL_WINDOW_START
        window_end = bar * 4 + 4.0
        if bar in fill_bars and window_start <= note.startBeats < window_end:
            continue  # this steady hit gives way to the fill
        result.append(note)
    # 2) insert the genre fill on each fill bar's last beat
    for bar in sorted(fill_bars):
        base = bar * 4
        for pitch, offset, duration, velocity, color in template:
            result.append(Note(pitch, base + offset, duration, velocity, color))
    return result
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_fills.py -q`
Expected: PASS (all 7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/fills.py backend/tests/test_fills.py
git commit -m "feat: add genre-specific drum fill module

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Wire the fill pass into the drums of both song builders

**Files:**
- Modify: `backend/app/generator.py`
- Test: `backend/tests/test_generator.py`

**Interfaces:**
- Consumes: `apply_fills` (Task 1); the existing `genre_family`, `_groove`, `_amapiano_drums`, `_generic_drums`.
- Produces: the drums part of `_generate_amapiano_song` and `_generate_generic_song` now passes through `apply_fills(...)` before `_groove(...)`.

- [ ] **Step 1: Write the failing integration test**

Add to `backend/tests/test_generator.py`:

```python
def test_drum_fills_vary_phrase_end_bars():
    # bars 4 and 8 (indices 3 & 7) are fill bars; bar 1 (index 0) is not. The fill changes
    # the last-beat note set, so the phrase-end last beats differ from bar 1's.
    draft = generate_song_draft(prompt="deep amapiano song", genre="Amapiano", key="A", scale="minor", bars=8)
    drums = next(p for p in draft.parts if p.role == "drums")

    def window_pitches(bar):
        lo, hi = bar * 4 + 2.9, bar * 4 + 4.05
        return sorted(n.pitch for n in drums.payload.notes if lo <= n.startBeats < hi)

    base = window_pitches(0)
    assert window_pitches(3) != base, "bar 4 should carry a fill"
    assert window_pitches(7) != base, "bar 8 should carry a fill"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_generator.py::test_drum_fills_vary_phrase_end_bars -q`
Expected: FAIL — without fills every bar's drums are identical, so `window_pitches(3) == window_pitches(0)`.

- [ ] **Step 3: Import `apply_fills`**

In `backend/app/generator.py`, find the harmony import line (added in Phase 3b):

```python
from .harmony import build_chords, chord_roots
```

Add directly below it:

```python
from .fills import apply_fills
```

- [ ] **Step 4: Wire the amapiano song drums**

In `_generate_amapiano_song`, change the drums part's `notes=` from:

```python
                notes=_groove(_amapiano_drums(bars), "drums", genre, key, bars, prompt),
```

to:

```python
                notes=_groove(apply_fills(_amapiano_drums(bars), family=genre_family(genre), bars=bars), "drums", genre, key, bars, prompt),
```

- [ ] **Step 5: Wire the generic song drums**

In `_generate_generic_song`, the `role_notes` dict's `drums` entry currently reads:

```python
        "drums": _groove(_generic_drums(bars), "drums", genre, key, bars, prompt),
```

Change it to:

```python
        "drums": _groove(apply_fills(_generic_drums(bars), family=family, bars=bars), "drums", genre, key, bars, prompt),
```

- [ ] **Step 6: Run the new test + full suite**

Run: `cd backend && ./.venv/Scripts/python -m pytest -q`
Expected: PASS — the new fill integration test, plus all existing tests (fills add notes on fill bars but no existing test pins exact drum counts; `sum(...) > 100` and determinism still hold).

If any pre-existing assertion fails because it pinned an exact pre-3c drum count or position, update it and note it in the task report. (At plan-writing time, no such assertion exists.)

- [ ] **Step 7: Commit**

```bash
git add backend/app/generator.py backend/tests/test_generator.py
git commit -m "feat: apply genre drum fills at phrase ends in song drafts

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- New pure `fills.py` (`FILL_TEMPLATES` + `FILL_WINDOW_START` + `apply_fills`) → Task 1. Per-genre fills using only existing kit pitches → Task 1 templates (amapiano hat/shaker rush + open hat; afro kick-driven run; boom-bap 32nd snare roll). Fill window `[3.0,4.0)` and `offset+duration<=4.0` guard → Task 1 `_validate_tables`. Fill bars = phrase ends `((bar+1)%4==0)` plus final bar → Task 1 `_fill_bars` (tested for 2/4/8). Drop base hits in window, insert fill → Task 1 `apply_fills` (tested). Deterministic, input untouched, `ValueError` on unknown family, empty→empty → Task 1 tests. Fill pass runs before groove at both song drums points → Task 2. Only the drums part changes; bass/chords/log-drum/melody, payloads, contracts, request, UI untouched → Task 2 (only the two drums `notes=` args change). Determinism preserved end-to-end → existing determinism tests stay green. All spec sections covered. Turnarounds, section dynamics, non-drum fills are explicit Non-Goals, intentionally absent.

**Placeholder scan:** No TBD/TODO; every step contains complete code.

**Type consistency:** `apply_fills(notes: list[Note], *, family: str, bars: int) -> list[Note]` is defined in Task 1 and called identically in Task 2 (amapiano passes `family=genre_family(genre)`, generic passes `family=family`). `FILL_TEMPLATES` keys, `_KNOWN_FAMILIES`, the generator's `genre_family` outputs, and `_GENERIC_FAMILIES` are the same `{"amapiano","afro","hiphop"}` set. `FillNote` tuple shape `(pitch, offset, duration, velocity, color)` is consumed consistently in `_validate_tables` and `apply_fills`.
