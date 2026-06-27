---
title: Phase 3b — Genre-specific Harmony (Chords + Progression-following Bass)
phase: "3b"
date: 2026-06-27
status: approved-for-planning
repository: C:\Users\HP\Vocals APP\fl-connector
branch: phase-3b-genre-harmony  (stacked on phase-3a-swing-humanization; rebase onto master once 3a's PR merges)
---

# Phase 3b Design: Genre-specific Harmony

## Context

After Phase 3a the generator *feels* played (swing + humanization), but afro and
hip-hop drafts still **borrow Amapiano's harmony**: `_generate_generic_song` builds
its chords with `_amapiano_chords(...)` ([generator.py:581](../../../backend/app/generator.py)),
and both afro and hip-hop share one `_generic_bass(...)`. Worse, the bass ignores the
chord progression entirely — it pulses on the tonic root + fifth no matter which chord
is sounding, so on non-tonic bars the low end and the harmony disagree.

Melody is already genre-specific (`_afro_melody`, `_hiphop_melody`, `_amapiano_melody`).
The harmonic layer is the gap. This sub-project gives each genre its own **chord
voicings** and a **bass that follows the chord progression**, so a draft sounds like the
genre it claims to be.

This is the second of the Phase 3 sub-projects. The third (fills / bar-to-bar variation)
stays a separate spec.

## Decisions already made (from brainstorming)

- **Priority is genre *identity* (harmony), not staticness.** Fills, turnarounds, and
  bar-to-bar variation are explicitly Phase 3c, not here.
- **Genres in scope:** `afro` and `hiphop` get their own harmony; `amapiano` is
  *refined* (its ad-hoc 4 chord shapes become one coherent loop). **Trap stays folded
  into the `hiphop` family** — no new family.
- **Harmonic depth:** genre-appropriate progression + chord *quality* + *register*,
  with a single fixed progression per genre. **No** voice-leading/inversions, **no**
  multiple progressions, **no** seed-selected progression variety (all deferred).
- **Bass follows the progression** — bass plays the root of each bar's chord, so the
  low end and harmony agree. This is the central architectural decision: chords and bass
  must share one progression source of truth.
- **Chord rhythm stays sustained** (one voicing per bar). Chord stabs / rhythmic
  comping are Phase 3c.

## Hard scope boundary (must stay honest)

This pass changes **pitches and note counts** of the chord and bass parts (unlike 3a,
which preserved count and touched only timing/velocity). It does **not** touch drums,
log-drum, or melody builders; does **not** add fills or variation; and makes **no**
`Note`/`SongDraft` contract, request, or UI changes. The Phase 3a groove pass is
unchanged and still wraps every part (chords role → velocity drift only, never swung).

## Goals

1. A standalone, pure, **deterministic** `harmony.py` module that owns each genre's
   progression, chord voicings, and the per-bar bass root.
2. Per-genre chord voicings (amapiano lush 9th pads, afro bright triad+add9, boom-bap
   jazzy 7ths) in genre-appropriate registers.
3. A bass that **follows the progression** in each genre's own rhythm (amapiano deep
   sub-pulse, afro rolling bounce, boom-bap sparse swung 808).
4. Generation wires chords + bass through the new module automatically; contracts,
   request, and UI unchanged; output stays byte-identical across runs.

## Non-Goals

- Drum / log-drum / melody changes (untouched).
- Chord stabs, rhythmic comping, fills, turnarounds, bar-to-bar variation (Phase 3c).
- Voice-leading, inversions, multiple/seed-selected progressions.
- Trap as its own family.
- The afro/hip-hop **single-pattern** payload builders (`_generate_afro_payload`,
  `_generate_hiphop_payload`) — they stay melody-only; they are not chord drafts.

---

## Design

### 1. New module — `backend/app/harmony.py`

Pure, standard-library only, mirroring the `groove.py` precedent. It owns the genre
harmonic identity; `generator.py` keeps owning rhythm/arrangement and calls in.

```python
@dataclass(frozen=True)
class GenreHarmony:
    progression: tuple[int, ...]  # diatonic scale degrees per bar (0 = tonic), cycles
    voicing: tuple[int, ...]      # diatonic stack offsets in scale STEPS from the chord root
    chord_octave: int             # semitone shift applied to the whole voicing (register)
    chord_sustain: float          # durationBeats of each sustained chord (must be <= 4)
    chord_velocity: float         # base velocity for chord notes
    chord_color: int              # FL piano-roll color for chords (8, matching today)
    bass_octave: int              # semitone shift from the in-pool chord root to the bass root
```

`GENRE_HARMONY: dict[str, GenreHarmony]` keyed by family (`amapiano`, `afro`, `hiphop`),
with an import-time guard asserting the keys match the generator's known families (same
pattern as `groove._validate_tables`).

**Voicings use diatonic stacking** so every chord tone is in-key and can never clash
with the scale-based melody/log-drum. A `voicing` offset `s` means "the scale degree
`progression[bar] + s`". Offsets `(0, 2, 4)` = triad, `(0, 2, 4, 6)` = 7th, `+8` adds the
9th. A small helper resolves a (possibly >6) diatonic degree to a MIDI pitch by wrapping
octaves over the 7 scale degrees from `_scale_notes`.

Concrete tables (roman numerals shown for review; the producer approved these):

| Family | `progression` (degrees) | Roman | `voicing` | Quality | `chord_octave` | `chord_sustain` | `bass_octave` |
|---|---|---|---|---|---|---|---|
| `amapiano` | (0, 5, 2, 6) | i – VI – III – VII | (0,2,4,6,8) | 9th pad (lush) | 0 | 3.7 | −12 |
| `afro` | (0, 4, 5, 3) | I – V – vi – IV | (0,2,4,8) | triad + add9 (bright) | +12 | 2.8 | −12 |
| `hiphop` | (1, 4, 0, 3) | ii – v – i – iv | (0,2,4,6) | diatonic 7th (jazzy) | 0 | 2.5 | −24 |

(Diatonic degrees resolve against whichever scale `infer_scale` picks — usually minor —
so qualities stay in key. Roman numerals above describe the minor-key reading.)

### 2. Public functions

```python
def build_chords(family: str, key: str, scale: str, bars: int) -> list[Note]:
def chord_roots(family: str, key: str, scale: str, bars: int) -> list[int]:
```

- **`build_chords`** — for each bar, take `progression[bar % len]` as the chord root
  degree, resolve each `voicing` offset to a pitch, shift by `chord_octave`, and emit a
  sustained `Note(pitch, startBeats=bar*4, durationBeats=chord_sustain, velocity=chord_velocity, color=chord_color)`.
  Count per draft = `bars * len(voicing)`.
- **`chord_roots`** — returns one MIDI root per bar: the chord root degree resolved to a
  pitch, shifted by `bass_octave`. This is the single source of truth the bass follows.
  Both functions are **pure and deterministic** (no randomness — the seeded feel is added
  later by the groove pass).

An unknown `family` raises `ValueError`; `bars <= 0` returns `[]`/`[]`.

### 3. Integration — `backend/app/generator.py`

Genre **bass rhythm** stays in `generator.py` (it is arrangement, genre-flavored) but now
consumes `chord_roots(...)` so every bass note lands on the current bar's root:

- `_amapiano_bass(roots, bars)` — keep today's deep sub-pulse offsets/durations; the
  per-bar `root` comes from `roots[bar]`; the existing "fifth" passing tone becomes
  `root + 7`.
- `_afro_bass(roots, bars)` — **new**: rolling syncopated 8th-bounce (root / octave /
  fifth), more notes than today's generic bass.
- `_hiphop_bass(roots, bars)` — **new**: sparse 808 — root on the downbeat (long) plus a
  pickup and an octave pop; swung by the groove pass (bass role keeps `swing_enabled`).

`_generic_bass` is **removed** (afro and hip-hop no longer share one bass).

Wiring touch points (each still wrapped by the existing `_groove(...)`):
- `_generate_amapiano_song`: chords → `build_chords("amapiano", key, scale, bars)`;
  bass → `_amapiano_bass(chord_roots("amapiano", key, scale, bars), bars)`.
- `_generate_generic_song(family, ...)`: chords → `build_chords(family, key, scale, bars)`;
  bass → `_afro_bass`/`_hiphop_bass` on `chord_roots(family, key, scale, bars)` (dispatch
  by family, mirroring the existing `_FAMILY_MELODY` table — add a `_FAMILY_BASS` map).
- `_generate_amapiano_payload`: the conditional chord block uses `build_chords("amapiano", …)`;
  its inline bass follows `chord_roots("amapiano", …)`.

`genre_family(genre)` already yields the family. No signature/contract changes to
`generate_payload` / `generate_song_draft`. `_amapiano_chords` is replaced by
`build_chords("amapiano", …)` and removed.

### 4. Determinism & contracts

- **Deterministic:** progressions/voicings are fixed constants — no new randomness. The
  groove pass still adds its seeded drift on top, so `generate_song_draft` /
  `generate_payload` called twice with identical args remain **byte-identical** (the
  existing determinism tests stay green).
- **Contracts:** `chord_octave`/`bass_octave` are chosen so all pitches stay in 0–127;
  `chord_sustain <= 4` and chords start on exact bar boundaries, so
  `startBeats + durationBeats <= bars*4` holds; velocities stay in `[0,1]`; `color = 8`.
  The groove boundary clamp from 3a still applies.

### 5. Testing

- **Unit (`backend/tests/test_harmony.py`)**:
  - Every `build_chords` pitch is a member of the key/scale's pitch classes (in-key);
    all pitches are 0–127; count == `bars * len(voicing)`.
  - `chord_roots` length == `bars`; the sequence cycles `progression` and each root sits
    in the bass register (== resolved progression root + `bass_octave`).
  - **Genre distinctness:** amapiano, afro, and hip-hop yield different chord pitch sets
    for the same key/scale/bars.
  - **Determinism:** identical inputs → identical output (pure function).
  - Boundary: `chord_sustain + bar_start <= bars*4` for every chord; unknown family raises
    `ValueError`; `bars=0` → `[]`.
- **Integration (`backend/tests/test_generator.py`)**:
  - Afro and hip-hop drafts' chord pitches now **differ** from the amapiano draft's
    (genre identity); a hip-hop draft's bass roots **follow** its progression (bass root on
    a non-tonic bar differs from bar 1).
  - Every generated draft still satisfies the contract; determinism + structural tests
    stay green.
  - Existing assertions that pin exact pre-3b chord/bass counts or pitches are updated to
    the new genre voicings (documented per test in the plan).

---

## Decisions

- **D1** Harmony lives in a separate pure `harmony.py` module (not inlined) — generators
  own rhythm/arrangement, harmony owns progressions/voicings; isolated and unit-testable,
  matching the `groove.py` precedent.
- **D2** One **shared progression** per genre is the single source of truth; `build_chords`
  and `chord_roots` both read it, guaranteeing bass and chords agree.
- **D3** **Diatonic stacking** for voicings — every chord tone is in-key, so chords never
  clash with the scale-based melody/log-drum; genre differs by stack depth + register +
  sustain + velocity.
- **D4** Fixed progressions: amapiano i–VI–III–VII, afro I–V–vi–IV, boom-bap ii–v–i–iv.
- **D5** Bass **follows** the per-bar chord root in each genre's own rhythm; `_generic_bass`
  is removed; afro/hip-hop get dedicated bass builders.
- **D6** Pitches/counts of chords + bass change (a generation-quality change); drums,
  log-drum, and melody are untouched; no contract/request/UI changes.
- **D7** Fully deterministic (fixed constants); the seeded groove pass still wraps output,
  keeping reproducibility.
- **D8** Branch `phase-3b-genre-harmony` is **stacked on** `phase-3a-swing-humanization`
  (which is in review as PR #1); it rebases onto master once 3a merges. Codex reviews the
  `phase-3a-swing-humanization..HEAD` diff.

## Rollout / Review

Small reviewable commits: `harmony.py` (tables + `build_chords` + `chord_roots`) with unit
tests → generator wiring (amapiano song + payload) → generic-song wiring (afro/hip-hop
chords + new bass builders) with updated integration tests. All existing tests stay green
except the chord/bass assertions intentionally changed by the new voicings.
