---
project: FL Connector (FL Studio 2025 connector)
session: Phase 2a — live mixer + transport writes
date: 2026-06-25
repo: C:\Users\HP\Vocals APP\fl-connector  (its own git repo)
branch: phase-2a-live-mixer-bridge  (stacked on phase-0-1-foundation-midi, UNMERGED)
head: 476b42f
status: code-complete; per-task AND final whole-branch reviews CLEAN; deferred minors cleared (476b42f); ONLY live FL acceptance (Task 7) remains
---

# Continue Here — FL Connector Phase 2a

## TL;DR
Phase 2a extends the read-only Flapi bridge with reversible LIVE WRITES (tempo
sync + per mixer-track name/volume/pan/select/mute/solo), each behind an explicit
per-action Apply. All 6 code tasks are implemented and passed per-task spec+quality
review. **Two things remain: (1) the final whole-branch review, and (2) your manual
live FL acceptance.** Backend 93 tests pass, frontend 12 pass, build clean.

## Branch / commit state
- Branch `phase-2a-live-mixer-bridge` is stacked on `phase-0-1-foundation-midi`
  (merge-base `7850fcc`). HEAD `b8c61f2`. 9 commits:
  - `604505b` spec, `a0821d5` plan
  - `8254bae` T1 run_bridge_write + transport refactor
  - `1177ecc` T2 set_project_tempo
  - `b3bb2fd` T3 set_mixer_track (name/volume/pan)
  - `265f5f4` T4 select/mute/solo toggles
  - `b932d48` T5 bridge write endpoints
  - `433b9cf` T6 frontend controls, `b8c61f2` T6 fix (track-control state reset)
- Phase 0+1 branch (`phase-0-1-foundation-midi`, 17 commits) is also still UNMERGED,
  awaiting Codex review. Phase 2a rebases onto master once Phase 0+1 merges.

## What shipped (Phase 2a)
- `backend/app/bridge.py`: `run_bridge_write(fl_code, message, client_factory)` helper
  (factored out of `run_transport_action`, which now delegates to it). Write functions:
  `set_project_tempo(bpm)` (via `general.processRECEvent(midi.REC_Tempo, round(bpm*1000),
  midi.REC_Control | midi.REC_UpdateControl)`), `set_mixer_track(index, *, name, volume,
  pan)` (name embedded via `json.dumps` — injection-safe), `select_mixer_track(index)`,
  `set_mixer_track_mute(index)` / `set_mixer_track_solo(index)` (bodyless TOGGLES — the
  snapshot carries no mute/solo state and FL toggles natively; this refines the spec's
  `{on}`). The read-only probe stays write-free.
- `backend/app/main.py`: `POST /api/bridge/tempo`, `/mixer/{index}`, `/mixer/{index}/select`,
  `/mixer/{index}/mute`, `/mixer/{index}/solo` — each returns a `BridgeSnapshot`, maps
  `ValueError`→400. Request models `BridgeTempoRequest`, `BridgeMixerTrackRequest`.
- `frontend/src/{api.js,App.jsx,styles.css}` + `BridgePanel.test.jsx`: exported
  `BridgeTrackControls` + `BridgePanel`; per-track name/volume/pan Apply + Select/Mute/Solo
  buttons; "Sync tempo to song draft" button; all disabled unless bridge connected.

## Honest platform boundary (unchanged)
Flapi taps FL's MIDI Controller scripting API: it can write mixer/channels/transport
but CANNOT insert plugins or place notes. Plugin insertion stays manual; notes go via
the Piano Roll `.pyscript` / Phase 1 MIDI export.

## NEXT ACTIONS (in order)
1. ~~**Run the final whole-branch review**~~ DONE (2026-06-26, Opus, range
   `7850fcc..b8c61f2`): CLEAN — ready to merge, zero Critical/Important. Independently
   verified name path is injection-safe (ast-parsed every dangerous input) and the
   REC_Tempo encoding matches the documented FL stub (live verify still required).
   Re-ran suites: 93 backend + 12 frontend pass, build ok. All 5 carry-over minors
   triaged DEFER; the two cheapest were then cleared in commit `476b42f` (tests for
   name + mute/solo index validation, dedupe bounds check → backend now 95 passed).
   Remaining deferred (cosmetic, left as-is): in-function `import pytest` x4; coarse
   bpm boundary test values.
2. **Live FL acceptance (Task 7, user-run — I cannot drive FL):** start backend +
   frontend, enable the Flapi controller scripts in FL's MIDI settings, refresh the
   Bridge panel to `connected`, then exercise each write and confirm in FL (and that
   Ctrl+Z reverses them). Steps are Task 7 in the plan. **Critical to verify:** the
   `REC_Tempo` encoding actually moves FL's tempo (D2 — flagged for live verification;
   if it no-ops, fix the flags/encoding).
3. After both pass: `finishing-a-development-branch` (likely keep-as-is for Codex
   review, or merge once Phase 0+1 lands).

## Then: Phase 2b and beyond
- **Phase 2b:** Channel Rack writes (channel naming/levels) — separate spec, same pattern.
- **Phase 3:** broader music quality (genre-specific generation, swing/humanization).
- **Phase 4:** Rebuild/stem-analysis improvements.

## Resume / run commands
```powershell
cd 'C:\Users\HP\Vocals APP\fl-connector\backend'
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```
```powershell
cd 'C:\Users\HP\Vocals APP\fl-connector\frontend'
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```
Verify: backend `cd backend && .\.venv\Scripts\python -m pytest -q` (93 passed);
frontend `cd frontend && npm test` (12 passed) + `npm run build`.

## How to resume next chat
Say: "Continue FL Connector Phase 2a from docs/SESSION_HANDOFF_PHASE_2A.md." First
action: run the final whole-branch review (package already at
`.superpowers/sdd/review-7850fcc..b8c61f2.diff`), then coordinate the live FL acceptance.

SDD progress ledger: `.superpowers/sdd/progress.md` (Tasks 1–6 marked complete).
Spec: `docs/superpowers/specs/2026-06-24-phase-2a-live-mixer-bridge-design.md`.
Plan: `docs/superpowers/plans/2026-06-24-phase-2a-live-mixer-bridge.md`.
