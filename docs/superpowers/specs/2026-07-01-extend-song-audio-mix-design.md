# Extend Song — Extended Audio Mix (Design)

Date: 2026-07-01
Status: Approved (brainstorming) — ready for implementation planning
Part 1 of 2 of the "song extension" effort. Part 2 (editable longer FL project) reuses this
design's arrangement plan + per-stem extended WAVs and is a separate spec/plan/build.

## Context

The user produces amapiano/deep-house songs in Suno AI. Suno tracks are ~4 minutes; the user needs
6–7 minute versions. Suno gives them **separated stems** (drums, bass, chords, vocals, etc.).

FL Connector's Rebuild workspace already ingests stems and analyzes them (tempo, key, per-stem
role). Nothing currently *lengthens* a song. Amapiano and deep house are loop/groove genres, so a
good 6–7 min version is not "play the 4 min twice" — it is a producer/DJ-style **extended mix**:
a longer structure (longer intro build → main groove → breakdown → drop → outro) built from the
song's groove, with layers dropping in and out.

## Decisions (from brainstorming)

- **Output:** both an extended audio mix (this spec) and, later, an editable longer FL project
  (sub-project 2).
- **Input:** separated stems (already the Rebuild upload format).
- **Arrangement:** **impose a genre arrangement** built from the song's groove — do NOT rely on
  detecting the original's sections (the current analysis fakes sections).
- **Vocals:** **place once** through the main sections (the original vocal performance stays intact
  in the middle; instrumental sections extend around it). Not looped.
- **Loop source:** **auto-pick** a beat-aligned phrase from the song's steady middle.
- **Genres:** amapiano and **deep house** (deep house is an extension-only template here; it is not
  a generator genre).
- **Tempo:** keep Suno's tempo; no time-stretching to a different BPM.

## Goal

From a Rebuild project's uploaded stems, produce a 6–7 minute **extended-mix WAV** (plus per-stem
extended WAVs) by arranging beat-aligned stem loops into a genre template, with the vocal placed
once through the main block.

## Architecture

A new **"Extend Song"** action on a Rebuild project. It runs a dedicated **light** background job
(tempo + beatgrid + per-stem role only — NOT the heavy `basic_pitch` MIDI transcription), builds a
pure **arrangement plan**, and an audio renderer in the analysis worker turns that plan + the stem
audio into the extended WAV(s).

```
stems (uploaded)  ──light analyze──▶  tempo, bar grid, roles, vocal duration
                                              │
                          build_extension_plan(genre, tempo, loop_bars, target_seconds, roles, vocal_seconds)
                                              │  ExtensionPlan = [ExtensionSection(name,bars,active_roles,is_main)]
                                              ▼
   pick mid-song loop phrase per stem  ──▶  audio renderer (worker: numpy + soundfile)
                                              │  tile loops in active sections; vocal placed once in Main block;
                                              │  equal-power crossfades at seams/joins; sum; normalize
                                              ▼
                                    extended-mix.wav  (+ per-stem extended WAVs)
```

## Components

### 1. `backend/app/extension_plan.py` (pure, no audio, no I/O)
- `@dataclass ExtensionSection(name: str, bars: int, active_roles: list[str], is_main: bool)`.
- `@dataclass ExtensionPlan(sections: list[ExtensionSection], loop_bars: int, tempo_bpm: float)`
  with helpers: `total_bars()`, `total_seconds()`, and `main_span_bars()`.
- `build_extension_plan(*, genre: str, tempo_bpm: float, loop_bars: int, target_seconds: float,
  roles: list[str], vocal_seconds: float | None) -> ExtensionPlan`:
  - Chooses the genre template (`amapiano` or `deep_house`; unknown genre → `amapiano` fallback).
  - Sizes the contiguous **Main/Drop** block to ≈ `vocal_seconds` (rounded to whole bars; if no
    vocal, uses the template's default main length).
  - Scales the instrumental Intro/Build/Breakdown/Outro section repeats so `total_seconds()` lands
    within the target window (default target 390 s; accepted 360–420 s).
  - Filters each section's `active_roles` to the roles actually present in `roles`.
  - Deterministic. Unit-tested with no audio.

### 2. Genre templates (data inside `extension_plan.py`)
Frozen tables, one per genre, each an ordered list of `(name, relative_bars, active_roles, is_main)`.
Example shape (amapiano): `Intro`(drums,percussion) → `Build`(+bass,+log_drum) →
`Main`(all, is_main, vocal) → `Breakdown`(chords, no drums) → `Drop`(all, is_main, vocal) →
`Outro`(drums,bass). Deep house analogous (kick/hats intro → +bass/chords build → main → chord
breakdown → drop → outro). An import-time guard validates every template's roles are within the
known role set.

### 3. Loop selection (`extension_plan.py` helper, pure)
`choose_loop_window(total_bars: int, loop_bars: int) -> int` → the start bar of a beat-aligned
phrase from the song's steady middle (centered near 50%, clamped away from the first/last phrase).
Default `loop_bars = 16` (fallback 8 when the song is too short). Pure bar math; unit-tested.

### 4. Audio renderer (`backend/analysis_worker/extend.py`; numpy + soundfile)
- Input: decoded stems (mono/stereo arrays + sample rate), tempo/bar grid, per-stem role, the
  `ExtensionPlan`, and the loop window.
- For each stem, allocate an output buffer of `total_bars * samples_per_bar`. In each section where
  the stem's role is active, **tile** its loop segment. The **vocal role** honours `vocalMode`
  (`place_once` | `loop` | `drop`): `place_once` (default) places the original vocal audio once
  across the contiguous Main/Drop block (silence elsewhere); `loop` treats the vocal like any other
  loopable layer; `drop` omits the vocal entirely (instrumental extended mix).
- Apply short **equal-power crossfades** at section seams and loop joins.
- **Sum** stems, **peak-normalize** to avoid clipping, write `extended/extended-mix.wav` and
  `extended/stems/<role>.wav` under the project dir.
- Pure DSP helpers (`loop_segment`, `place_tiles`, `equal_power_crossfade`, `samples_per_bar`) are
  separated from file I/O so they are unit-testable on tiny synthetic arrays.

### 5. Job, store, and API
- A dedicated **extend job** mirroring the existing `AnalysisJob`/`AnalysisJobRunner` pattern
  (status/progress/stage/message, background execution, result path). It calls a **light analysis**
  (librosa `beat_track` + existing `infer_role`; no `basic_pitch`).
- `POST /api/reconstructions/{project_id}/extend` with body `{genre, targetSeconds, vocalMode}`
  → starts the job (409 if one is already running; 400 on no stems).
- The reconstruction project payload gains an `extendJob` + `extendedMix` (relative path,
  durationSeconds) block.
- `GET /api/reconstructions/{project_id}/extended-mix` streams the WAV (404 until complete).

### 6. Frontend — "Extend Song" card (Rebuild workspace)
Below the existing panes: genre select (Amapiano / Deep House), a **target length** slider
(6:00–7:00), vocal handling (default *Place once*, with the other two modes available), a **Create
extended mix** button, a progress bar (polls like the analysis job), then an `<audio>` player and a
**Download** button when done. Two `api.js` methods: `extendReconstruction(id, body)` and
`extendedMixUrl(id)`.

## Error handling

- No stems → `400`. Extend job already running → `409`. Bridge/FL not involved (pure local audio).
- Renderer failures (decode error, unusable tempo) → job `error` with a clear message; never crash
  the server.
- A stem too short to yield the loop phrase → fall back to a smaller `loop_bars`, then to tiling the
  whole stem; recorded as a warning on the result.

## Testing

- **`extension_plan`**: template selection + fallback; vocal-anchored main-block sizing; target
  scaling within 360–420 s; role filtering to present stems; `choose_loop_window` bounds;
  determinism. All pure, no audio.
- **Renderer DSP helpers**: `samples_per_bar`, `loop_segment` bounds, `place_tiles` offsets, and
  `equal_power_crossfade` (sums to ~unity power) on small synthetic arrays; one **smoke test**
  renders a valid WAV whose length ≈ `plan.total_seconds()` from tiny synthetic stems.
- **Job/API**: endpoint starts a job and returns status; a stubbed renderer drives a
  complete→download path; 400/409/404 paths.
- **Frontend**: the Extend card renders, calls `extendReconstruction`, shows progress, and exposes
  the player/download on completion.

## Out of scope (deliberate)

- The editable longer **FL project** (sub-project 2 — reuses this `ExtensionPlan` + the per-stem
  extended WAVs and the Phase 4 send-to-FL).
- Real section detection of the original song.
- Time-stretching/pitch-shifting to a different tempo/key.
- Genres beyond amapiano/deep house.

## Dependencies

Add `soundfile` to the analysis-worker environment (for WAV writing). `librosa`/`numpy` are already
present in that env.

## Acceptance (user-run, after build)

1. In a Rebuild project with Suno stems, open **Extend Song**, pick genre + target length, **Create
   extended mix**.
2. When the job completes, the player plays a 6–7 min version: recognizable groove, the vocal intact
   through the middle, instrumental intro/build/breakdown/outro extending it, no clicks at section
   seams.
3. **Download** yields `extended-mix.wav` of ≈ the chosen length.
