---
project: FL Connector (FL Studio 2025 connector)
session: Phase 0+1 — foundation fixes + one-drag MIDI export
date: 2026-06-24
repo: C:\Users\HP\Vocals APP\fl-connector  (its own git repo)
branch: phase-0-1-foundation-midi  (16 commits ahead of master, UNMERGED)
status: code-complete, green, awaiting Codex review + live FL acceptance
---

# Continue Here — FL Connector

## TL;DR
Analyzed the Codex-built FL Connector, fixed real bugs (Phase 0), and added the
biggest "seamless" feature — one-drag multi-track MIDI export (Phase 1). All work
is on branch `phase-0-1-foundation-midi`, kept unmerged so **Codex can review**.
Backend 86 tests pass, frontend 9 pass, build clean.

## What this app is
Local-first FastAPI (`:8765`) + React/Vite (`:5173`) tool for FL Studio 2025.
Turns prompts into MIDI note payloads, generates built-in mastering chains,
reconstructs uploaded stems into editable FL blueprints, and has a read-only
Flapi live bridge (+ transport play/stop). See `docs/ARCHITECTURE.md`.

## Agreed 5-phase roadmap (user is a producer; Codex reviews each change)
- **Phase 0 — foundation bug fixes. DONE.**
- **Phase 1 — one-drag multi-track MIDI export (seamless spine, no Flapi needed). DONE.**
- **Phase 2 — deeper live FL automation via Flapi** (tempo/key sync, track
  select/name, volume/pan; spike plugin-insert for live mastering). User's FL 2025
  is fully set up with Flapi + loopMIDI, so live testing is possible. *Next to spec.*
- **Phase 3 — broader music quality** (real genre-specific generation beyond
  Amapiano, swing/humanization, fills). Note: Phase 0 made afro/hiphop/trap songs
  *coherent but simple* — their chords currently reuse Amapiano voicings; genre
  voicings are deferred to here.
- **Phase 4 — Rebuild/stem-analysis improvements** (per-stem role detection,
  better MIDI reconstruction, more sound matches).

Each phase = its own spec → plan → implement → review cycle.
Spec: `docs/superpowers/specs/2026-06-24-foundation-fixes-and-midi-export-design.md`
Plan: `docs/superpowers/plans/2026-06-24-foundation-fixes-and-midi-export.md`

## What shipped this session

### Phase 0 — foundation fixes
1. Coherent multi-part song generation for EVERY genre. `backend/app/generator.py`
   added `genre_family()`, `_generate_generic_song()`, role-filtered `_arrangement()`.
   (Bug: afro/hip/trap previously produced a single melody with a mismatched
   arrangement; "trap" dispatched inconsistently.)
2. Real single-concurrency: `_analysis_runner()` is now a shared singleton so the
   job lock actually serializes. Interrupted jobs recover on startup. Migrated
   deprecated `@app.on_event` → FastAPI `lifespan`. `backend/app/main.py`.
3. Resilient `events()` (skips malformed/non-dict lines → `/api/health` & `/api/events`
   can't 500). Atomic, thread-safe FL-file writes via `_atomic_write_text` (unique
   temp name + process write lock; safe under FastAPI's threadpool on Windows).
   `backend/app/store.py`.
4. Accurate `docs/ARCHITECTURE.md` (old top-level one described an unrelated project).

### Phase 1 — one-drag MIDI export
5. `backend/app/midi_export.py` — dependency-free Standard MIDI File type-1 writer
   (`song_to_midi`, `payload_to_midi`; 96 PPQ; conductor track + one named track per
   part; excludes muted notes; pitches preserved verbatim).
6. Endpoints `GET /api/songs/{id}/export-midi` and `GET /api/payloads/{id}/export-midi`
   (`audio/midi` download, 404s). `backend/app/main.py`.
7. Frontend: "Download Song MIDI (all parts)" + per-part download buttons, busy-guarded.
   `frontend/src/api.js`, `App.jsx`, `styles.css`, `App.test.jsx`.

## Verification (at HEAD)
- Backend: `cd backend && ./.venv/Scripts/python -m pytest -q` → **86 passed**.
- Frontend: `cd frontend && npm test` → **9 passed**; `npm run build` → clean.
- Every task passed spec-compliance + code-quality review; review findings fixed
  (notably a muted-note export bug and a Windows concurrent-write race).

## Outstanding
1. **Live FL acceptance (Task 8 — user-run, I cannot drive FL):** in the app,
   Generate a song → "Download Song MIDI (all parts)" → drag the `.mid` into the
   FL Studio 2025 Playlist → confirm each part lands on its own channel at correct
   pitch/timing/tempo. Steps in the plan's Task 8.
2. **Codex review:** `git diff master..phase-0-1-foundation-midi`. Merge to `master`
   when satisfied.
3. **Known follow-up (out of Phase 0+1 scope):** pre-existing TOCTOU in
   `backend/app/analysis_jobs.py` `start()` — consider fixing in Phase 2.

## How to resume next chat
Say: "Continue FL Connector from docs/SESSION_HANDOFF_2026-06-24.md." Likely next
action: brainstorm + spec **Phase 2 (deeper live Flapi automation)**, or merge
Phase 0+1 after Codex review.

### Run the app
```powershell
cd 'C:\Users\HP\Vocals APP\fl-connector\backend'
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```
```powershell
cd 'C:\Users\HP\Vocals APP\fl-connector\frontend'
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```
Open http://127.0.0.1:5173

## Branch commits (master..HEAD)
Includes the design spec + plan, then per-task `feat`/`fix` commits each followed
by a `refactor`/`test`/`fix` review-fix commit, ending with
`fix: address final review (thread-safe atomic writes, ASCII filenames, table guard)`.
