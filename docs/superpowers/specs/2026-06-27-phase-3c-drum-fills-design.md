---
title: Phase 3c — Genre-specific Drum Fills at Phrase Ends
phase: "3c"
date: 2026-06-27
status: approved-for-planning
repository: C:\Users\HP\Vocals APP\fl-connector
branch: phase-3c-drum-fills  (stacked on phase-3b-genre-harmony; rebase onto master once 3a/3b PRs merge)
---

# Phase 3c Design: Genre-specific Drum Fills

## Context

After Phases 3a (swing/humanization) and 3b (genre harmony), drafts feel played and
sound like their genre — but the **drum pattern is byte-identical every bar**.
`_amapiano_drums`/`_generic_drums` ([generator.py:263](../../../backend/app/generator.py))
loop the same hits over `range(bars)`, so an 8-bar draft is the same bar eight times. The
loop never breathes. This sub-project adds a **genre-specific drum fill on the back end of
each 4-bar phrase**, the single most recognizable "this isn't a static loop" signal.

This is the third and final Phase 3 sub-project (3a feel, 3b harmony, 3c motion).

## Decisions already made (from brainstorming)

- **Scope is drum fills only.** Turnarounds on bass/melody and full per-section dynamics
  (intro sparse → drop full) are deferred — not this phase.
- **Genre-specific fills** — each family gets its own fill, consistent with the groove
  (`GROOVE_TEMPLATES`) and harmony (`GENRE_HARMONY`) genre work.
- **Back-of-bar fill** — the groove plays normally through the bar; only the **last beat**
  (beats 3.0–4.0) breaks into the fill, so momentum holds.
- **Cadence: every 4-bar phrase** — fill the last bar of each 4-bar group, plus the final
  bar of the draft always (so short drafts still breathe).
- **Deterministic** — fixed fill patterns per genre, no randomness; the 3a groove pass
  still humanizes them on top.

## Hard scope boundary (must stay honest)

This phase changes only the **drums** part of song drafts (`generate_song_draft`). It does
NOT touch bass, chords, log-drum, or melody; does NOT change the single-pattern payloads
(`generate_payload` has no drums part); and makes NO `Note`/`SongDraft` contract, request,
or UI changes. Fills use each genre's existing kit pitches (no new pads required). The 3a
groove pass and 3b harmony are unchanged.

## Goals

1. A standalone, pure, **deterministic** `fills.py` module that, given a drum note list,
   a genre family, and the bar count, returns the list with a genre fill on each phrase-end
   bar's last beat.
2. Per-genre fills (amapiano hat/shaker rush, afro kick-driven run, boom-bap snare roll)
   using only each genre's documented kit pitches.
3. Generation applies the fill pass to the drums part automatically, *before* the groove
   pass (so fills are humanized too); contracts/request/UI unchanged.

## Non-Goals

- Turnarounds or variation on bass/chords/log-drum/melody (deferred).
- Full per-section dynamics / section-aware generation (deferred).
- Fills on the single-pattern payloads (they have no drums part).
- User-facing fill controls; randomized/seed-varied fills (fills are fixed and automatic).

---

## Design

### 1. New module — `backend/app/fills.py`

Pure, standard-library only, mirroring `groove.py`/`harmony.py`. The drums part pipeline
in the generator becomes:

```python
_groove(apply_fills(_drums(bars), family=<family>, bars=bars), "drums", ...)
```

`apply_fills` runs first (inserts fill notes), then the existing `_groove` humanizes the
whole drum list including the fill. Only the drums assembly point changes.

### 2. Fill model

```python
FILL_WINDOW_START = 3.0  # beats; the fill occupies the last beat [3.0, 4.0) of a fill bar

# (pitch, offset_in_bar, durationBeats, velocity, color)
FillNote = tuple[int, float, float, float, int]
FILL_TEMPLATES: dict[str, tuple[FillNote, ...]]  # keyed by amapiano | afro | hiphop
```

An import-time guard asserts `FILL_TEMPLATES` keys equal the known families and every
template offset lies in `[FILL_WINDOW_START, 4.0)` with `offset + duration <= 4.0`.

**Fill bars** (0-indexed) = every bar where `(bar + 1) % 4 == 0`, plus the final bar
`bars - 1`, deduped. Examples: 4 bars → {3}; 8 bars → {3, 7}; 16 bars → {3, 7, 11, 15};
2 bars → {1}.

```python
def apply_fills(notes: list[Note], *, family: str, bars: int) -> list[Note]:
```

For each fill bar `b`: drop base notes whose `startBeats` lies in
`[b*4 + FILL_WINDOW_START, b*4 + 4.0)` (the steady hits in the last beat give way), then
append the family's `FILL_TEMPLATES` notes with `startBeats = b*4 + offset`. Non-fill bars
are untouched. Unknown `family` raises `ValueError`; an empty `notes` list returns `[]`.
The function returns a NEW list (input untouched) and preserves note order is not required
(generation re-sorts later via `_payload`).

### 3. Per-genre fills (each genre's existing kit only)

Existing kit pitches/colors: kick 36 (color 5), snare/clap 39 (color 3), closed hat 42
(color 2), open hat 46 (color 4), shaker 70 (color 6). Concrete templates (the producer
approved the character; exact values pinned here):

- **Amapiano** — shaker/hat rush into the next phrase:
  - closed hat 42: 3.0 (v0.50), 3.25 (v0.62), 3.5 (v0.74), 3.75 (v0.88), dur 0.1, color 2
  - shaker 70: 3.0, 3.125, 3.25, 3.375, 3.5, 3.625, 3.75, 3.875 (32nds), velocity ramp
    0.30→0.62, dur 0.06, color 6
  - open hat 46: 3.75 (v0.60), dur 0.18, color 4
- **Afro** — kick-driven percussive run:
  - kick 36: 3.0 (v0.85), 3.5 (v0.80), dur 0.18, color 5
  - snare 39: 3.25 (v0.50), 3.75 (v0.82), dur 0.14, color 3
  - closed hat 42: 3.0, 3.25, 3.5, 3.75 (v0.50), dur 0.1, color 2
- **Boom-bap (hiphop)** — classic snare roll:
  - snare 39: 3.0, 3.125, 3.25, 3.375, 3.5, 3.625, 3.75, 3.875 (32nd roll), velocity
    crescendo 0.40→0.90, dur 0.08, color 3

All offsets are in `[3.0, 4.0)` with `offset + duration <= 4.0`, so every fill note stays
inside its bar.

### 4. Integration — `backend/app/generator.py`

Two touch points, both wrapping the existing `_groove(...)` call around `apply_fills`:

- `_generate_amapiano_song` drums part:
  `notes=_groove(apply_fills(_amapiano_drums(bars), family=genre_family(genre), bars=bars), "drums", genre, key, bars, prompt)`
- `_generate_generic_song` `role_notes["drums"]`:
  `_groove(apply_fills(_generic_drums(bars), family=family, bars=bars), "drums", genre, key, bars, prompt)`

`genre_family(genre)` already yields the family. `import` adds `from .fills import apply_fills`.
No other builder, contract, request, or UI changes.

### 5. Determinism & contracts

- **Deterministic:** templates are fixed constants — no randomness. The seeded groove pass
  still wraps the drums, so `generate_song_draft` stays byte-identical across runs.
- **Contracts:** every fill note has `offset + duration <= 4.0`, so `startBeats + duration`
  stays within the bar; velocities are in `[0,1]`; colors `0–15`; pitches reuse existing kit
  values (all valid). The 3a groove boundary clamp still applies after the fill pass.

### 6. Testing

- **Unit (`backend/tests/test_fills.py`)**:
  - Fill bars (e.g., bar 3 of a 4-bar input, bars 3 & 7 of 8) have their `[3.0,4.0)` base
    hits replaced and the family fill present; non-fill bars are byte-identical to input.
  - Fill-bar selection: 4 bars → only bar 3; 8 → bars 3 & 7; 2 → bar 1 (final-bar rule).
  - Genre distinctness: amapiano, afro, hiphop produce different fill-note sets.
  - Determinism: same inputs → identical output; input list not mutated.
  - Every output note satisfies the contract (`note.validate()`), and fill notes stay in
    `[bar*4, bar*4+4.0)`.
  - Unknown family raises `ValueError`; empty list returns `[]`.
- **Integration (`backend/tests/test_generator.py`)**: in an 8-bar draft, the drums part's
  bar-4 and bar-8 last-beat notes differ from bar 1's; the draft still satisfies the
  contract; determinism + existing structure tests stay green.

---

## Decisions

- **D1** Fills live in a separate pure `fills.py` module — generators own the base pattern,
  fills own the phrase-end variation; isolated and unit-testable, matching the
  `groove.py`/`harmony.py` precedent.
- **D2** Fill pass runs BEFORE the groove pass, so fill notes are humanized like everything
  else.
- **D3** Fill window is the last beat `[3.0, 4.0)`; the groove plays normally through beats
  1–3 so momentum holds.
- **D4** Fill bars = each 4-bar phrase end `((bar+1) % 4 == 0)` plus the final bar.
- **D5** Genre-specific fills using only each genre's existing kit pitches (no new pads;
  FPC routing unaffected).
- **D6** Deterministic fixed templates; the seeded groove pass still wraps the drums,
  preserving reproducibility.
- **D7** Only the drums part of song drafts changes; bass/chords/log-drum/melody, payloads,
  contracts, request, and UI are untouched.
- **D8** Branch `phase-3c-drum-fills` is stacked on `phase-3b-genre-harmony`; it rebases
  onto master once the 3a/3b PRs merge. Codex reviews the `phase-3b-genre-harmony..HEAD`
  diff.

## Rollout / Review

Small reviewable commits: `fills.py` (templates + `apply_fills`) with unit tests →
generator drums wiring (both song builders) with the integration test. All existing tests
stay green (drums note counts on fill bars change, but no test pins exact drum counts).
