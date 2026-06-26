---
title: Phase 3a — Genre-aware Swing & Humanization
phase: "3a"
date: 2026-06-26
status: approved-for-planning
repository: C:\Users\HP\Vocals APP\fl-connector
branch: phase-3a-swing-humanization  (off master)
---

# Phase 3a Design: Genre-aware Swing & Humanization

## Context

The note generator (`backend/app/generator.py`) places every note on a rigid grid
with constant velocities — e.g. `_amapiano_drums` hats are exactly `step * 0.5`
beats with velocity `0.46`/`0.58`, and the afro/hiphop builders are similarly
quantized. Drafts therefore sound stiff and machine-like. This sub-project adds a
**genre-aware groove pass** that applies swing (pushing offbeats late) plus subtle
seeded timing/velocity humanization, so parts feel played rather than programmed.

This is the first of three Phase 3 sub-projects (the others — genre-specific
voicings, and fills/variation — are separate specs). Scope was deliberately limited
to *feel*: timing and velocity only.

## Decisions already made (from brainstorming)

- **Automatic per-genre** — each genre family carries a built-in groove template;
  generation applies it. No request-contract or UI/frontend changes.
- **Deterministic / seeded** — randomness is seeded from stable song inputs, so the
  same prompt reproduces the same humanized result and the transform is testable.
- Velocity *accent* patterns (groove emphasis beyond random jitter) are **deferred**
  to a later pass; they slot into the same `GrooveTemplate` when wanted.

## Hard scope boundary (must stay honest)

This pass changes only `startBeats` and `velocity` of existing notes. It does **not**
change pitches, chord voicings, or progressions (Phase 3b), and does **not** add drum
fills, turnarounds, or bar-to-bar variation (Phase 3c). Note count is preserved.

## Goals

1. A standalone, pure, deterministic `groove.py` module that swings + humanizes a
   list of notes given a genre family, a role, and a seed.
2. Per-genre groove templates (amapiano, afro, hiphop) with sensible feel.
3. Per-role intensity so it sounds musical — sustained chords are NOT swung and get
   near-zero timing jitter; drums/melody get the full treatment.
4. Generation applies the pass to every part automatically; the `Note`/`SongDraft`
   contracts, the request, and the UI are unchanged.

## Non-Goals

- Voicing/progression/pitch changes (Phase 3b).
- Fills, turnarounds, bar-to-bar variation (Phase 3c).
- User-facing swing/humanize controls (deferred; the control model is automatic).
- Velocity accent/groove-emphasis templates (deferred).

---

## Design

### 1. New module — `backend/app/groove.py`

A `GrooveTemplate` dataclass (frozen) per genre family:

```python
@dataclass(frozen=True)
class GrooveTemplate:
    swing: float          # fraction of the swing grid offbeats are pushed late (0..~0.5)
    swing_grid: float     # beats per subdivision whose offbeats swing (0.5 = 8th, 0.25 = 16th)
    timing_jitter: float  # max +/- beats of seeded micro-timing
    velocity_jitter: float# max +/- velocity of seeded variation
```

`GROOVE_TEMPLATES: dict[str, GrooveTemplate]` keyed by family (`amapiano`, `afro`,
`hiphop`), each tuned per genre (e.g. amapiano/afro a rolling 16th-grid swing; hiphop
a laid-back 8th-grid swing). A validation guard at import time asserts the table keys
match the generator's known families.

Per-role intensity table `ROLE_INTENSITY: dict[str, tuple[float, float, bool]]`
mapping role -> `(timing_mult, velocity_mult, swing_enabled)`:
- `drums`, `log_drum`, `melody`: full timing+velocity, swing on.
- `bass`: moderate timing+velocity, swing on.
- `chords`: `timing_mult = 0.0`, small `velocity_mult`, **swing off** (no smear).
- unknown role: a safe default (moderate, swing on).

### 2. `apply_groove`

```python
def apply_groove(notes: list[Note], *, family: str, role: str, seed: int) -> list[Note]:
```

Pure function returning NEW `Note`s (input untouched). For each note, in order:

1. **Swing** (only if the role's `swing_enabled`): let `g = template.swing_grid`.
   Compute the note's position within its bar-relative swing pair; if it lands on an
   offbeat subdivision (its position modulo `2*g` is approximately `g`), push it late
   by `delay = template.swing * g`. On-beat notes are unchanged.
2. **Timing jitter**: `start += rng.uniform(-tj, tj) * timing_mult`, where
   `tj = template.timing_jitter`. Then clamp `start = max(0.0, start)`.
3. **Velocity jitter**: `velocity += rng.uniform(-vj, vj) * velocity_mult`, where
   `vj = template.velocity_jitter`. Clamp to `[0.05, 1.0]`.
4. Round `start` and `velocity` to 4 dp (consistent with existing note precision) and
   emit a new `Note` with the same pitch/duration/color.

`rng = random.Random(seed)` is created once per call and advanced per note in note
order, so output is fully determined by `(notes, family, role, seed)`. Notes keep
their original order (no re-sort). An unknown `family` raises `ValueError`.

### 3. Stable seed derivation

```python
def groove_seed(prompt: str, key: str, bars: int, genre: str, role: str) -> int:
```

Returns a process-stable integer seed derived via `hashlib.sha256` of a delimited
string of the inputs (NOT Python's salted `hash()`), so the same song reproduces
across runs and the seed differs per role (parts don't jitter in lockstep).

### 4. Integration — `backend/app/generator.py`

At each part-assembly point, wrap the role's note list:
`apply_groove(notes, family=<family>, role=<role>, seed=groove_seed(prompt, key, bars, genre, role))`.
Touch points:
- `_generate_amapiano_song` — the five role note-lists (drums/bass/chords/log_drum/melody).
- `_generate_generic_song` — the four role note-lists (drums/bass/chords/melody).
- `_generate_amapiano_payload`, `_generate_afro_payload`, `_generate_hiphop_payload` —
  apply with a representative role (these single-pattern payloads carry one role's feel;
  use the role that dominates the payload, e.g. `log_drum`/`melody`, documented in the plan).

`genre_family(genre)` already yields the family. No signature/contract changes.

### 5. Error handling

`apply_groove` raises `ValueError` on an unknown family; generator callers always pass
a known family (from `genre_family`). Empty note lists return `[]`. Clamping guarantees
valid velocities/non-negative starts regardless of template values.

### 6. Testing

- **Unit (`backend/tests/test_groove.py`)**:
  - An offbeat note (on the swing grid's offbeat) is delayed by exactly `swing*grid`
    with `timing_jitter=0`/`velocity_jitter=0` template (swing isolated).
  - An on-beat note is unchanged under the same zero-jitter template.
  - With a chord role, the note is NOT swung and timing is unchanged (timing_mult 0),
    even with a swinging template.
  - Velocity always lands in `[0.05, 1.0]`; start always `>= 0`, across a stress input.
  - **Determinism**: same `(notes, family, role, seed)` → identical output across two
    calls; a different `seed` changes the jitter.
  - `groove_seed` is stable (recomputing equal inputs gives the same int) and
    role-sensitive (different role → different seed).
  - Unknown family raises `ValueError`; empty list returns `[]`.
- **Integration (`backend/tests/test_generator.py`)**: a generated draft's offbeat
  notes are shifted off the rigid grid as expected; the note **count per part is
  unchanged**; the draft still satisfies the contract. Existing generator tests that
  assert exact rigid positions/velocities are updated to the post-groove values (or
  relaxed to assert structure/count rather than exact grid floats), documented per
  test in the plan.

---

## Decisions

- **D1** Groove is a separate `groove.py` pure module, not inlined into builders —
  generators own pitch/pattern, groove owns feel; isolated and unit-testable.
- **D2** Deterministic: `random.Random(seed)` with a `hashlib`-derived stable seed;
  Python's salted `hash()` is explicitly NOT used.
- **D3** Per-role intensity; chords are never swung and get ~zero timing jitter to
  avoid smearing sustained pads.
- **D4** Swing rule: offbeat subdivisions of the genre's `swing_grid` are delayed by
  `swing*grid`; on-beat positions unchanged.
- **D5** Note count is preserved; only `startBeats`/`velocity` change; `start>=0`,
  velocity clamped `[0.05,1.0]`, both rounded to 4 dp.
- **D6** No request/contract/UI changes; the pass is internal to generation.
- **D7** Velocity accent patterns and user controls are deferred to later work.
- **D8** Branch `phase-3a-swing-humanization` is cut from master; Codex reviews the
  `master..HEAD` diff.

## Rollout / Review

- Small reviewable commits: `groove.py` module + templates + `apply_groove` +
  `groove_seed` (with unit tests) → generator integration (with updated integration
  tests). All existing tests stay green (adjusting only the rigid-position assertions
  that the groove pass intentionally changes).
