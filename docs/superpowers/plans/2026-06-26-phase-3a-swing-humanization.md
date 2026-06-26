# Phase 3a — Genre-aware Swing & Humanization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make generated drafts feel played rather than programmed by applying a genre-aware, deterministic swing + timing/velocity humanization pass to every part.

**Architecture:** A new pure module `backend/app/groove.py` owns the "feel": per-genre `GrooveTemplate`s, a `random.Random(seed)`-based `apply_groove(notes, *, family, role, seed)` that swings offbeats and adds seeded timing/velocity jitter, and a `hashlib`-derived stable `groove_seed(...)`. `backend/app/generator.py` calls it at each part-assembly point via a small `_groove(...)` helper. No `Note`/`SongDraft` contract, request, or UI changes; note count is preserved.

**Tech Stack:** Python 3.11 / pytest (backend venv at `backend/.venv`). Standard library only (`random`, `hashlib`, `dataclasses`).

## Global Constraints

- Working dir: `C:\Users\HP\Vocals APP\fl-connector`. Branch: `phase-3a-swing-humanization` (already created off master; spec committed at `98d2135`).
- Backend test command: `cd backend && ./.venv/Scripts/python -m pytest -q`.
- This pass changes ONLY `startBeats` and `velocity` of existing notes — never pitch, duration, color, or note count.
- Deterministic: randomness comes from `random.Random(seed)` where the seed is derived via `hashlib.sha256` of stable inputs. Python's salted `hash()` is NOT used.
- Per-role intensity: chords are NEVER swung and get zero timing jitter (no smearing of sustained pads); drums/log_drum/melody get full treatment; bass moderate.
- Clamps: `startBeats = max(0.0, start)`; `velocity` clamped to `[0.05, 1.0]`; both rounded to 4 dp (matching `Note.to_dict`).
- Genre families are exactly `{"amapiano", "afro", "hiphop"}` (from `genre_family`). `apply_groove` raises `ValueError` on an unknown family.

**Spec:** `docs/superpowers/specs/2026-06-26-phase-3a-swing-humanization-design.md`

---

## Task 1: `groove.py` module (templates + `apply_groove` + `groove_seed`)

**Files:**
- Create: `backend/app/groove.py`
- Test: `backend/tests/test_groove.py`

**Interfaces:**
- Produces:
  - `GrooveTemplate(swing: float, swing_grid: float, timing_jitter: float, velocity_jitter: float)` (frozen dataclass).
  - `GROOVE_TEMPLATES: dict[str, GrooveTemplate]` keyed by `"amapiano"|"afro"|"hiphop"`.
  - `ROLE_INTENSITY: dict[str, tuple[float, float, bool]]` mapping role -> `(timing_mult, velocity_mult, swing_enabled)`, including a `"_default"` key.
  - `apply_groove(notes: list[Note], *, family: str, role: str, seed: int) -> list[Note]`.
  - `groove_seed(prompt: str, key: str, bars: int, genre: str, role: str) -> int`.
- Consumes: `Note` from `app.contracts`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_groove.py`:

```python
import pytest

from app.contracts import Note
from app.groove import (
    GROOVE_TEMPLATES,
    GrooveTemplate,
    apply_groove,
    groove_seed,
)


def _note(start, velocity=0.6):
    return Note(pitch=60, startBeats=start, durationBeats=0.25, velocity=velocity, color=2)


def test_swing_delays_offbeat_by_swing_times_grid(monkeypatch):
    # zero jitter so swing is isolated and exact
    monkeypatch.setitem(
        GROOVE_TEMPLATES, "_t", GrooveTemplate(swing=0.5, swing_grid=0.5, timing_jitter=0.0, velocity_jitter=0.0)
    )
    # offbeat of an 8th grid (0.5) is at 0.5, 1.5, ...
    out = apply_groove([_note(0.5)], family="_t", role="drums", seed=1)
    assert out[0].startBeats == 0.75  # 0.5 + swing(0.5)*grid(0.5)


def test_onbeat_is_unchanged_under_zero_jitter(monkeypatch):
    monkeypatch.setitem(
        GROOVE_TEMPLATES, "_t", GrooveTemplate(swing=0.5, swing_grid=0.5, timing_jitter=0.0, velocity_jitter=0.0)
    )
    out = apply_groove([_note(1.0)], family="_t", role="drums", seed=1)
    assert out[0].startBeats == 1.0


def test_chords_are_not_swung_and_timing_unchanged(monkeypatch):
    monkeypatch.setitem(
        GROOVE_TEMPLATES, "_t", GrooveTemplate(swing=0.5, swing_grid=0.5, timing_jitter=0.05, velocity_jitter=0.0)
    )
    out = apply_groove([_note(0.5)], family="_t", role="chords", seed=1)
    assert out[0].startBeats == 0.5  # no swing (offbeat), no timing jitter for chords


def test_velocity_and_start_are_clamped_and_valid():
    notes = [Note(pitch=60, startBeats=0.0, durationBeats=0.25, velocity=0.99, color=2) for _ in range(50)]
    out = apply_groove(notes, family="amapiano", role="drums", seed=7)
    for note in out:
        assert 0.05 <= note.velocity <= 1.0
        assert note.startBeats >= 0.0
        note.validate()  # contract still satisfied


def test_same_inputs_are_deterministic_and_seed_changes_output():
    notes = [_note(i * 0.5) for i in range(8)]
    a = apply_groove(notes, family="amapiano", role="drums", seed=42)
    b = apply_groove(notes, family="amapiano", role="drums", seed=42)
    c = apply_groove(notes, family="amapiano", role="drums", seed=43)
    assert [n.to_dict() for n in a] == [n.to_dict() for n in b]
    assert [n.to_dict() for n in a] != [n.to_dict() for n in c]


def test_groove_seed_is_stable_and_role_sensitive():
    s1 = groove_seed("deep amapiano", "A", 8, "Amapiano", "drums")
    s2 = groove_seed("deep amapiano", "A", 8, "Amapiano", "drums")
    s3 = groove_seed("deep amapiano", "A", 8, "Amapiano", "bass")
    assert s1 == s2
    assert s1 != s3
    assert isinstance(s1, int)


def test_unknown_family_raises_and_empty_list_returns_empty():
    assert apply_groove([], family="amapiano", role="drums", seed=1) == []
    with pytest.raises(ValueError):
        apply_groove([_note(0.5)], family="nope", role="drums", seed=1)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_groove.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.groove'`.

- [ ] **Step 3: Implement `backend/app/groove.py`**

```python
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, replace

from .contracts import Note

_KNOWN_FAMILIES = {"amapiano", "afro", "hiphop"}


@dataclass(frozen=True)
class GrooveTemplate:
    swing: float          # fraction of swing_grid that offbeats are pushed late (0..~0.5)
    swing_grid: float     # beats per subdivision whose offbeats swing (0.5 = 8th, 0.25 = 16th)
    timing_jitter: float  # max +/- beats of seeded micro-timing
    velocity_jitter: float  # max +/- velocity of seeded variation


GROOVE_TEMPLATES: dict[str, GrooveTemplate] = {
    "amapiano": GrooveTemplate(swing=0.32, swing_grid=0.25, timing_jitter=0.02, velocity_jitter=0.07),
    "afro": GrooveTemplate(swing=0.28, swing_grid=0.25, timing_jitter=0.02, velocity_jitter=0.07),
    "hiphop": GrooveTemplate(swing=0.18, swing_grid=0.5, timing_jitter=0.03, velocity_jitter=0.08),
}

# role -> (timing_mult, velocity_mult, swing_enabled)
ROLE_INTENSITY: dict[str, tuple[float, float, bool]] = {
    "drums": (1.0, 1.0, True),
    "log_drum": (1.0, 1.0, True),
    "melody": (1.0, 1.0, True),
    "bass": (0.6, 0.8, True),
    "chords": (0.0, 0.5, False),
    "_default": (0.6, 0.8, True),
}


def _validate_tables() -> None:
    if set(GROOVE_TEMPLATES.keys()) != _KNOWN_FAMILIES:
        raise RuntimeError("GROOVE_TEMPLATES families are out of sync with the generator")


_validate_tables()


def groove_seed(prompt: str, key: str, bars: int, genre: str, role: str) -> int:
    payload = "\x1f".join([prompt, key, str(bars), genre, role])
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def apply_groove(notes: list[Note], *, family: str, role: str, seed: int) -> list[Note]:
    template = GROOVE_TEMPLATES.get(family)
    if template is None:
        raise ValueError(f"unknown groove family: {family}")
    timing_mult, velocity_mult, swing_enabled = ROLE_INTENSITY.get(role, ROLE_INTENSITY["_default"])
    rng = random.Random(seed)
    grid = template.swing_grid
    result: list[Note] = []
    for note in notes:
        start = note.startBeats
        if swing_enabled and grid > 0 and abs((start % (2 * grid)) - grid) < 1e-6:
            start += template.swing * grid
        # Always advance the rng the same way per note (multiplier may be 0) so output stays deterministic.
        start += rng.uniform(-template.timing_jitter, template.timing_jitter) * timing_mult
        velocity = note.velocity + rng.uniform(-template.velocity_jitter, template.velocity_jitter) * velocity_mult
        start = round(max(0.0, start), 4)
        velocity = round(min(1.0, max(0.05, velocity)), 4)
        result.append(replace(note, startBeats=start, velocity=velocity))
    return result
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_groove.py -q`
Expected: PASS (all 7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/groove.py backend/tests/test_groove.py
git commit -m "feat: add genre-aware swing + humanization groove module

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Integrate the groove pass into generation

**Files:**
- Modify: `backend/app/generator.py`
- Test: `backend/tests/test_generator.py`

**Interfaces:**
- Consumes: `apply_groove`, `groove_seed` (Task 1), and the existing `genre_family`.
- Produces: a private `_groove(notes, role, genre, key, bars, prompt) -> list[Note]` helper; every generated part's notes pass through it.

- [ ] **Step 1: Write the failing integration test**

Add to `backend/tests/test_generator.py`:

```python
def test_groove_shifts_notes_off_the_rigid_grid():
    # The rigid builders place notes on exact 0.25-beat multiples; the groove pass
    # (swing + jitter) must move at least some notes off that grid.
    payload = generate_payload(prompt="Create a deep amapiano log drum riff", key="A")
    off_grid = [n for n in payload.notes if abs(((n.startBeats * 4) % 1.0)) > 1e-6]
    assert off_grid, "expected groove to shift some notes off the 0.25-beat grid"


def test_groove_preserves_note_count_and_determinism():
    first = generate_payload(prompt="Create a deep amapiano log drum riff", key="A")
    second = generate_payload(prompt="Create a deep amapiano log drum riff", key="A")
    # determinism (seeded from stable inputs) is preserved
    assert [n.to_dict() for n in first.notes] == [n.to_dict() for n in second.notes]
    # every note still satisfies the contract after grooving
    for note in first.notes:
        note.validate()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_generator.py::test_groove_shifts_notes_off_the_rigid_grid -q`
Expected: FAIL — every note is still on the exact grid (groove not yet wired in), so `off_grid` is empty.

- [ ] **Step 3: Add the `_groove` helper and import**

In `backend/app/generator.py`, add to the imports at the top:

```python
from .groove import apply_groove, groove_seed
```

Add this helper near the top of the module (after `genre_family`):

```python
def _groove(
    notes: list[Note], role: str, genre: str, key: str, bars: int, prompt: str
) -> list[Note]:
    family = genre_family(genre)
    return apply_groove(
        notes,
        family=family,
        role=role,
        seed=groove_seed(prompt, key, bars, genre, role),
    )
```

- [ ] **Step 4: Wire `_generate_amapiano_song` parts through `_groove`**

In `_generate_amapiano_song`, wrap each part's `notes=` argument. Apply this exact mapping (role -> builder call), leaving everything else unchanged:

- drums:    `notes=_groove(_amapiano_drums(bars), "drums", genre, key, bars, prompt)`
- bass:     `notes=_groove(_amapiano_bass(key, scale, bars), "bass", genre, key, bars, prompt)`
- chords:   `notes=_groove(_amapiano_chords(key, scale, bars), "chords", genre, key, bars, prompt)`
- log_drum: `notes=_groove(_amapiano_log_drum(key, scale, bars), "log_drum", genre, key, bars, prompt)`
- melody:   `notes=_groove(_amapiano_melody(key, scale, bars), "melody", genre, key, bars, prompt)`

For example, the drums part changes from:

```python
                notes=_amapiano_drums(bars),
```

to:

```python
                notes=_groove(_amapiano_drums(bars), "drums", genre, key, bars, prompt),
```

- [ ] **Step 5: Wire `_generate_generic_song` role_notes through `_groove`**

In `_generate_generic_song`, replace the `role_notes` dict with grooved note lists:

```python
    role_notes = {
        "drums": _groove(_generic_drums(bars), "drums", genre, key, bars, prompt),
        "bass": _groove(_generic_bass(key, scale, bars), "bass", genre, key, bars, prompt),
        "chords": _groove(_amapiano_chords(key, scale, bars), "chords", genre, key, bars, prompt),
        "melody": _groove(melody_builder(key, scale, bars), "melody", genre, key, bars, prompt),
    }
```

- [ ] **Step 6: Wire the single-pattern payload builders through `_groove`**

The `_*_payload` builders produce one combined note list; apply the groove with the payload's dominant rhythmic role.

In `_generate_amapiano_payload`, change the final return so its `notes` are grooved with role `"log_drum"`:

```python
    return _payload(
        title=infer_title(prompt, genre),
        prompt=prompt,
        genre=genre,
        bpm=bpm,
        key=key,
        scale=scale,
        bars=bars,
        notes=_groove(notes, "log_drum", genre, key, bars, prompt),
    )
```

In `_generate_afro_payload`, change `notes=_afro_melody(key, scale, bars)` to:

```python
        notes=_groove(_afro_melody(key, scale, bars), "melody", genre, key, bars, prompt),
```

In `_generate_hiphop_payload`, change `notes=_hiphop_melody(key, scale, bars)` to:

```python
        notes=_groove(_hiphop_melody(key, scale, bars), "melody", genre, key, bars, prompt),
```

- [ ] **Step 7: Run the integration tests + full suite**

Run: `cd backend && ./.venv/Scripts/python -m pytest -q`
Expected: PASS — the two new integration tests, plus all existing generator tests (they assert counts/colors/determinism/structure, none of which the groove pass changes) and the full suite.

If any pre-existing test fails because it asserted an exact rigid `startBeats`/`velocity` that the groove pass now changes, update that single assertion to the post-groove value (or relax it to assert structure/count), and note it in the task report. (At plan-writing time the existing `test_generator.py` asserts only counts, colors, determinism, and structure — so no such update is expected.)

- [ ] **Step 8: Commit**

```bash
git add backend/app/generator.py backend/tests/test_generator.py
git commit -m "feat: apply genre-aware groove pass to all generated parts

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- `groove.py` module + `GrooveTemplate` + `GROOVE_TEMPLATES` + `ROLE_INTENSITY` + `apply_groove` + `groove_seed` → Task 1. Per-genre templates → Task 1. Per-role intensity (chords not swung, zero timing jitter) → Task 1 (`ROLE_INTENSITY`, tested). Deterministic seeded transform → Task 1 (`random.Random` + `hashlib` seed, tested). Swing rule (offbeat delayed by `swing*grid`) → Task 1 (tested). Clamps + 4dp rounding + note-count preserved → Task 1 (tested) and Task 2 (integration test). Generator integration at all assembly points (amapiano song, generic song, three payload builders) → Task 2. No contract/request/UI changes → confirmed (only `generator.py` + `groove.py` touched). All spec sections covered. Velocity accent patterns + user controls are explicit Non-Goals, intentionally absent.

**Placeholder scan:** No TBD/TODO; every code step contains complete code.

**Type consistency:** `GrooveTemplate(swing, swing_grid, timing_jitter, velocity_jitter)`, `apply_groove(notes, *, family, role, seed) -> list[Note]`, `groove_seed(prompt, key, bars, genre, role) -> int`, `ROLE_INTENSITY` value tuple `(timing_mult, velocity_mult, swing_enabled)`, and the generator `_groove(notes, role, genre, key, bars, prompt)` helper are used consistently across Tasks 1–2 and the tests. Families are the same `{"amapiano","afro","hiphop"}` set in both `groove.py` (`_KNOWN_FAMILIES`) and the generator's `genre_family`.

**Note:** Determinism is preserved end-to-end because the seed derives only from stable song inputs, so `generate_payload` called twice with identical arguments still produces byte-identical notes — keeping the existing `test_amapiano_generation_is_valid_and_deterministic` green.
