---
title: Foundation Fixes + One-Drag MIDI Export
phase: "0+1"
date: 2026-06-24
status: approved-for-planning
repository: C:\Users\HP\Vocals APP\fl-connector
---

# Phase 0+1 Design: Foundation Fixes + One-Drag MIDI Export

## Context

The FL Connector is a local-first FastAPI (`:8765`) + React/Vite (`:5173`) tool for
FL Studio 2025. It generates MIDI note payloads from prompts, generates built-in
mastering chains, reconstructs uploaded stems into editable FL blueprints, and
exposes a read-only Flapi live bridge (plus transport play/stop).

Current state: 68/68 backend tests pass and the frontend builds. The system is not
"broken" at the test level, but it has concrete correctness bugs and the core
"get the generated music into FL Studio" path is heavily manual (apply one part at
a time via a Piano Roll `.pyscript`).

This is the first of a five-phase roadmap. It combines the foundation bug fixes
(Phase 0) with the single biggest "seamless" win (Phase 1: one-drag multi-track
MIDI export), because both concern the generate -> apply path.

Later phases (out of scope here): Phase 2 deeper live Flapi automation, Phase 3
broader music quality, Phase 4 Rebuild/stem-analysis improvements.

## Goals

1. Fix the confirmed correctness bugs so the core flows are reliable.
2. Add a one-drag multi-track MIDI export so a whole song lands in FL in one action,
   with no Flapi required.

## Non-Goals

- Live Flapi write automation (tempo sync, track select, plugin insert) — Phase 2.
- Genre-specific musical richness / new genres / humanization — Phase 3.
- Stem-analysis accuracy improvements — Phase 4.
- Touching the outer HOME git repo or the unrelated `Vocals APP/docs/ARCHITECTURE.md`.

---

## Phase 0 — Foundation Fixes

### 0.1 Genre-correct song generation

**Problem:** In `app/generator.py`, `generate_song_draft` routes any genre containing
`"afro"` or `"hip"` to a **single melody part**, while `_arrangement()` still lists
drums/bass/log_drum as active. Only Amapiano produces a real multi-part song. Dispatch
is also inconsistent: `"trap"` routes to hip-hop for single-part generation but to
Amapiano for song generation.

**Fix:**
- Introduce one genre dispatch used by both `generate_payload` (single part) and
  `generate_song_draft` (song). Supported genre keys: `amapiano` (default),
  `afrobeats`, `hiphop`, `trap`.
- Every genre's song draft produces a coherent set of parts: `drums`, `bass`,
  `chords`, `melody`. Amapiano additionally includes `log_drum`.
- `_arrangement()` must only list `activeParts` that exist in the produced draft
  (parametrize the active-part sets by the roles actually present).
- Keep musical content minimal-but-correct. Reuse existing Amapiano part builders;
  for afro/hiphop/trap, provide simple coherent drum/bass/chord/melody patterns.
  Rich musicality is deferred to Phase 3.

**Success criteria / tests:**
- For each genre in {amapiano, afrobeats, hiphop, trap}: `generate_song_draft`
  returns >= 4 parts and validates.
- For every draft, each arrangement section's `activeParts` is a subset of the set
  of part roles present in `draft.parts`.
- `"trap"` resolves to the same genre family for both single and song generation.

### 0.2 Real single-concurrency for analysis

**Problem:** `app/main.py:_analysis_runner()` constructs a **new** `AnalysisJobRunner`
per request, so the instance-level `self._lock` never serializes concurrent
`/analyze` calls.

**Fix:** Construct one shared `AnalysisJobRunner` (module-level singleton or stored on
app state) and reuse it for all analyze/retry requests. The existing lock then
serializes correctly. Thread/`start()`/`run()` model unchanged.

**Success criteria / tests:**
- Two `start()` calls on the shared runner: the second raises
  `ReconstructionError("another analysis job is already running")`.
- `/analyze` and `/retry` use the same shared runner instance.

### 0.3 Recover interrupted jobs on startup

**Problem:** `AnalysisJobRunner.mark_interrupted_jobs()` exists but is never called, so a
backend restart leaves any in-flight project stuck in `analyzing` forever.

**Fix:** Call `mark_interrupted_jobs()` during startup (via the new lifespan handler).
Log the count of recovered projects.

**Success criteria / tests:**
- A project persisted with `status="analyzing"` and a running job is, after startup,
  read back as `status="error"` with job `status="interrupted"` and retryable.

### 0.4 Resilient events + health

**Problem:** `app/store.py:events()` calls `json.loads` on every line; one malformed or
truncated line raises and 500s both `/api/events` and `/api/health`. The events file
also grows unbounded.

**Fix:**
- `events()` skips blank/malformed lines (best-effort parse) and returns the valid
  tail rows.
- Ensure `/api/health` cannot 500 because of a bad event line.

**Success criteria / tests:**
- `events.jsonl` containing a garbage line still yields the valid rows with no
  exception.
- `/api/health` returns 200 with a corrupted events file present.

### 0.5 Atomic writes for FL-facing files

**Problem:** `app/store.py` writes `pending_payload.json`, `current_*.json`, and
`approved_mastering_plan.json` in place. If FL Studio reads mid-write it can get a
truncated file.

**Fix:** Add an `_atomic_write_text(path, text)` helper (write to a sibling `*.tmp`
then `os.replace`) and use it for all FL-facing and "current" JSON writes.

**Success criteria / tests:**
- The atomic helper writes the exact content and leaves no `.tmp` residue on success.
- Approve flows still write the FL payload/plan files correctly (existing tests pass).

### 0.6 Cleanup

**Fix:**
- Migrate the deprecated `@app.on_event("startup")` to a FastAPI `lifespan` handler
  that runs `STORE.ensure()`, `RECONSTRUCTION_STORE.ensure()`, the startup event log,
  and `mark_interrupted_jobs()`.
- Add an accurate `fl-connector/docs/ARCHITECTURE.md` describing the real connector
  (backend modules, data flow, FL integration surfaces, bridge). Do not modify the
  unrelated outer `Vocals APP/docs/ARCHITECTURE.md`.

**Success criteria / tests:**
- App starts via lifespan; startup work runs (verified by existing TestClient tests
  that trigger startup, plus the 0.3 interrupted-jobs test).
- No `on_event` deprecation warning from app code.

---

## Phase 1 — One-Drag Multi-Track MIDI Export

### 1.1 SMF writer module — `app/midi_export.py`

A dependency-free Standard MIDI File **type 1** writer. No `mido`.

**API:**
- `song_to_midi(draft: SongDraft) -> bytes`
- `payload_to_midi(payload: NotePayload) -> bytes`

**Format:**
- Header chunk `MThd`: format 1, ntrks = (1 conductor + N part tracks), division = 96 PPQ.
- Conductor track (track 0): sequence/track name meta (draft title), tempo meta
  (`round(60_000_000 / bpm)` microseconds per quarter note), time signature 4/4,
  then end-of-track.
- One track per part (in `applyOrder`): track name meta = part `patternName`; notes as
  note-on / note-off events; end-of-track.
- For a single `NotePayload`, emit conductor track + one part track (still format 1)
  named by the payload title.

**Note mapping:**
- `tick = round(beats * 96)`; note-off at `start + duration` ticks.
- `velocity = clamp(round(v * 127), 1, 127)`.
- Channel = part index (`applyOrder - 1`) modulo 16. **Pitches preserved verbatim**
  — no GM channel-10 drum remap (keeps FPC pad pitches intact). [Decision D2]
- Events within a track sorted by absolute tick (note-off before note-on at equal
  tick to avoid zero-length collisions); encoded with standard variable-length delta
  times.

**Success criteria / tests:**
- A small in-test SMF reader (or byte-level assertions) verifies: `MThd` format 1,
  correct ntrks, division 96; conductor tempo matches `60e6/bpm`; each part track name
  matches; note count and a sampled (pitch, start_tick, velocity) match the source.
- `payload_to_midi` round-trips a single payload's notes.

### 1.2 Endpoints — `app/main.py`

- `GET /api/songs/{song_id}/export-midi` -> `StreamingResponse`, media type
  `audio/midi`, `Content-Disposition` filename derived from the song title
  (sanitized), 404 if the song id is unknown.
- `GET /api/payloads/{payload_id}/export-midi` -> single-part MIDI, 404 if unknown.

**Success criteria / tests:**
- 200 + non-empty `audio/midi` body for a known song/payload id.
- 404 for unknown ids.

### 1.3 Frontend — `src/api.js`, `src/App.jsx`

- `api.exportSongMidi(id)` and `api.exportPayloadMidi(id)` using the existing
  `download()` helper.
- "Download Song MIDI (all parts)" button on the song-draft section; per-part
  "Download MIDI" button.
- Short inline hint: drag the `.mid` into the FL Studio Playlist or onto a Channel
  Rack slot; each track becomes its own channel/pattern.

**Success criteria / tests:**
- Frontend (vitest) test asserts the buttons call the correct API endpoints.
- `npm run build` succeeds.

### 1.4 Live acceptance (FL Studio 2025, user has it fully set up)

- Generate a song draft, click "Download Song MIDI", drag the `.mid` into FL 2025.
- Confirm: parts land on separate channels; pitches, timing, and tempo match the
  preview. Record any discrepancy as a follow-up.

---

## Testing Strategy

- Backend: extend the pytest suite; keep generation deterministic. All existing
  68 tests must continue to pass.
- Frontend: vitest component tests; production build must pass.
- Live: manual FL 2025 drag-in acceptance for the MIDI export.

## Decisions

- **D1** Hand-rolled SMF writer; zero new runtime dependencies.
- **D2** MIDI channels preserve exact pitches; no GM channel-10 drum remap.
- **D3** Spec and code commits live in the `fl-connector` git repo.
- **D4** Phase 0 makes afro/hip/trap songs correct and coherent, not yet musically
  rich (richness is Phase 3).

## Rollout / Review

- Implement Phase 0 then Phase 1 as small, reviewable commits in `fl-connector`.
- Codex reviews the diff after implementation.
