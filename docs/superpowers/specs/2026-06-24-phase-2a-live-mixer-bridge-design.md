---
title: Phase 2a — Live Mixer + Transport Writes
phase: "2a"
date: 2026-06-24
status: approved-for-planning
repository: C:\Users\HP\Vocals APP\fl-connector
branch: phase-2a-live-mixer-bridge  (stacked on phase-0-1-foundation-midi)
---

# Phase 2a Design: Live Mixer + Transport Writes

## Context

The FL Connector has a working read-only Flapi live bridge (`backend/app/bridge.py`):
`probe_bridge()` returns a `BridgeSnapshot` (mixer tracks, transport, version), and
`run_transport_action("play"|"stop")` is the one existing reversible write. The
bridge setup is verified ready on the target machine — the "Flapi Request"/"Flapi
Response" loopMIDI ports exist, the controller scripts are installed, and the
backend imports `flapi`/`mido`/`rtmidi`. The only manual step to connect is
enabling the controller scripts inside FL Studio's MIDI settings while FL runs.

This phase extends the bridge from read-only + play/stop to a set of **reversible
mixer and transport writes**, each behind an **explicit per-action Apply** in the
UI. It is Phase 2a of the roadmap; Phase 2b (Channel Rack writes) is a separate spec.

## Hard platform boundary (must stay honest)

Flapi taps FL Studio's **MIDI Controller scripting API**. That API can read/write
the mixer, channels, and transport, but it **cannot insert plugins into mixer
slots** and **cannot place notes**. Therefore:
- Live "mastering" can set track names/levels/routing but **cannot auto-add**
  Fruity EQ/Compressor/etc. Plugin insertion stays manual (existing click-paths).
- Note placement stays via the Piano Roll `.pyscript` and the Phase 1 MIDI export.

## Goals

1. A reusable `run_bridge_write` helper that all write actions share.
2. Live writes: project tempo sync; per mixer track name / volume / pan / select /
   mute / solo.
3. Per-action Apply controls in the Bridge panel; a "sync tempo to song draft" action.
4. Every write is reversible via FL's own undo; nothing writes without an explicit click.

## Non-Goals

- Channel Rack writes (Phase 2b).
- Plugin insertion / live mastering FX (impossible via the API).
- Note placement (use Phase 1 MIDI export or the Piano Roll script).
- A batch "apply everything" button (per-action was chosen; a batch convenience can come later).

---

## Design

### 1. Backend write helper — `backend/app/bridge.py`

Add `run_bridge_write(fl_code: str, message: str, client_factory=None) -> BridgeSnapshot`.
It uses the exact pattern already proven in `run_transport_action`: acquire
`_BRIDGE_PROBE_LOCK`, build a client (handle `ModuleNotFoundError` → disconnected,
other connect errors → disconnected), then `client.exec(fl_code)`, `client.exec(
READ_ONLY_FL_PROBE)`, read the snapshot, and return a `connected` snapshot with
`message`; on exec/probe failure return an `error` snapshot; always `client.close()`.

Refactor `run_transport_action` to call `run_bridge_write` (it becomes: validate the
action, then `run_bridge_write(f"import transport\n{command}", f"Live FL transport
action applied: {action}.")`). `READ_ONLY_FL_PROBE` stays free of write calls — the
existing invariant test `test_read_only_probe_does_not_include_write_actions` must
still pass.

### 2. Write functions — `backend/app/bridge.py`

Each validates its inputs (raising `ValueError` on bad input) and returns
`run_bridge_write(...)`:

- `set_project_tempo(bpm: float)` — validate `40 <= bpm <= 240`. FL code:
  `import general\nimport midi\ngeneral.processRECEvent(midi.REC_Tempo, <int(round(bpm*1000))>, midi.REC_Control | midi.REC_UpdateControl)`.
  Message: `f"Set FL project tempo to {bpm} BPM."`. The exact REC flags and the
  BPM*1000 encoding are verified against FL's MIDI scripting API and live testing
  during implementation (see Testing / Decisions D2).
- `set_mixer_track(index: int, *, name=None, volume=None, pan=None)` — validate
  `0 <= index <= 125`; at least one field provided; `name` non-empty and ≤ 100 chars;
  `0 <= volume <= 1`; `-1 <= pan <= 1`. FL code imports `mixer` and emits one line per
  provided field: `mixer.setTrackName(index, name)`, `mixer.setTrackVolume(index, volume)`,
  `mixer.setTrackPan(index, pan)`. Message summarizes which fields changed.
- `select_mixer_track(index: int)` — validate index; FL code `import mixer\nmixer.setTrackNumber(index)`.
- `set_mixer_track_mute(index: int, on: bool)` — `import mixer\nmixer.muteTrack(index, <1|0>)`.
- `set_mixer_track_solo(index: int, on: bool)` — `import mixer\nmixer.soloTrack(index, <1|0>)`.

All string interpolation into FL code uses only validated numeric indices/values and
a length-and-quote-sanitized name (no newlines/quotes), so the exec'd code can't be
injected through.

### 3. Endpoints — `backend/app/main.py`

Pydantic request models with validation, each returning the `BridgeSnapshot` dict:
- `POST /api/bridge/tempo` — `{ "bpm": float (40–240) }`
- `POST /api/bridge/mixer/{index}` — `{ "name"?: str, "volume"?: float, "pan"?: float }`
- `POST /api/bridge/mixer/{index}/select`
- `POST /api/bridge/mixer/{index}/mute` — `{ "on": bool }`
- `POST /api/bridge/mixer/{index}/solo` — `{ "on": bool }`

`ValueError` from a write function → `HTTPException(400)`. If FL is unreachable the
write function already returns a `disconnected`/`error` snapshot (status reflected in
the body), mirroring `run_transport_action`.

### 4. Frontend — `frontend/src/api.js`, `frontend/src/App.jsx`

- `api.js`: `bridgeSetTempo(bpm)`, `bridgeSetMixerTrack(index, body)`,
  `bridgeSelectTrack(index)`, `bridgeMuteTrack(index, on)`, `bridgeSoloTrack(index, on)`.
- `App.jsx` `BridgePanel`: each live track row (already rendered from the snapshot)
  gains inline editable **name / volume / pan** with an **Apply** button, plus
  **Select / Mute / Solo** buttons. Near the transport controls add a **"Sync tempo
  to song draft"** button (uses the current song draft's BPM; disabled when no song).
  All controls disabled unless `bridge.status === 'connected'` and not `busy`, exactly
  like the existing Play/Stop buttons. Each Apply calls the API, then sets the returned
  snapshot into state so the panel updates immediately, and shows a status message.

### 5. Error handling

Write functions never raise to the endpoint except on validation (`ValueError` → 400).
Connection/exec failures come back as a `disconnected`/`error` `BridgeSnapshot` whose
`message`/`errors` the UI already renders. The frontend wraps calls in the existing
`runTask` try/catch so a 400 surfaces via `setMessage`.

### 6. Testing

- **Unit** (`backend/tests/test_bridge.py` style, with an injected `FakeClient`):
  for each write function, assert the exact FL code `exec`'d, that the read-only probe
  is re-run, and that the returned snapshot is built; assert `ValueError` on invalid
  args (bad index/volume/pan/bpm/empty-name); assert `run_transport_action` still
  produces the same `exec` sequence after the refactor; the read-only-probe invariant
  test still passes.
- **Endpoint** (`backend/tests/`): each route returns a 200 snapshot via a monkeypatched
  write function; invalid bodies return 422/400.
- **Live acceptance** (user, FL open + controller scripts enabled): set tempo, rename a
  track, set its volume/pan, select/mute/solo it — confirm each in FL, and confirm FL's
  Ctrl+Z reverses them.

---

## Decisions

- **D1** Generalize `run_transport_action` into `run_bridge_write`; the read-only probe
  stays write-free (invariant test preserved).
- **D2** Tempo set via `general.processRECEvent(midi.REC_Tempo, round(bpm*1000), flags)`;
  exact flags/encoding verified against FL's scripting API + live testing. Unit tests use
  the fake client and do not depend on real FL. If `REC_Tempo` proves unreliable in live
  testing, the fallback (and its limitation) is documented rather than silently shipped.
- **D3** No auto-creating mixer tracks (FL's mixer tracks are fixed 0–125); writes target
  an explicit `index` supplied by the UI.
- **D4** Volume uses FL's 0–1 scale (~0.8 = unity), matching the existing snapshot values.
- **D5** Every write re-runs the read-only probe and returns a fresh `BridgeSnapshot` so
  the UI updates atomically.
- **D6** Branch `phase-2a-live-mixer-bridge` is stacked on `phase-0-1-foundation-midi`
  (Phase 0+1 is unmerged); Codex reviews the `phase-0-1-foundation-midi..HEAD` diff. It
  rebases onto master once Phase 0+1 merges.

## Rollout / Review

- Implement as small, reviewable commits: write helper + transport refactor → tempo →
  mixer track name/vol/pan → select/mute/solo → endpoints → frontend.
- All existing tests must stay green; live acceptance gates "done".
