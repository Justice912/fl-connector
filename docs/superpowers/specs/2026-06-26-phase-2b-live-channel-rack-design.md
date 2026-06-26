---
title: Phase 2b — Live Channel Rack Writes
phase: "2b"
date: 2026-06-26
status: approved-for-planning
repository: C:\Users\HP\Vocals APP\fl-connector
branch: phase-2b-live-channel-rack  (off master; Phase 0+1+2a already merged to master)
---

# Phase 2b Design: Live Channel Rack Writes

## Context

Phase 2a shipped reversible live **mixer + transport** writes over the Flapi bridge
(`backend/app/bridge.py`): `run_bridge_write(fl_code, message, client_factory)` execs a
one-shot FL script, re-runs the read-only probe, and returns a fresh `BridgeSnapshot`;
typed write functions (`set_project_tempo`, `set_mixer_track`, `select_mixer_track`,
`set_mixer_track_mute/solo`) build the FL code; thin FastAPI endpoints expose them; and
the React Bridge panel renders per-track Apply + Select/Mute/Solo controls. Phase 2a is
merged to master and its tempo encoding (D2) is live-verified.

This phase adds the symmetric capability for the **Channel Rack**: per-channel
name / volume / pan writes plus Select / Mute / Solo toggles, each behind an explicit
per-action Apply. It reuses every piece of 2a's write infrastructure. The one genuinely
new element is that the read-only probe currently returns **no channel data**, so 2b
must also surface channels in the `BridgeSnapshot`.

## Hard platform boundary (must stay honest)

Flapi taps FL Studio's **MIDI Controller scripting API**. It can read/write channel
names, levels, pan, and mute/solo/select state, but it **cannot create channels**,
**cannot load instruments/plugins into a channel**, and **cannot place notes**. This
phase renames / re-levels / toggles **existing** channels only. Adding instruments and
placing notes stay manual (existing click-paths / Piano Roll `.pyscript` / Phase 1 MIDI
export).

## Goals

1. Surface the Channel Rack in the read-only snapshot: a `channels` array plus
   `channelCount` and `selectedChannel`, using **global channel indexing**.
2. Live writes: per channel name / volume / pan (Apply), and Select / Mute / Solo toggles.
3. A "Channel Rack" section in the Bridge panel that mirrors the mixer-track controls,
   with Mute/Solo buttons reflecting live state.
4. Every write reversible via FL's own undo; nothing writes without an explicit click.

## Non-Goals

- Creating channels or loading instruments/plugins (impossible via the API).
- Note placement (use Phase 1 MIDI export or the Piano Roll script).
- Channel → mixer FX-track routing (`setTargetFxTrack`), channel color, and pitch —
  deferred. (The read-only "→ Insert N" routing display was considered and cut to keep
  scope a strict mirror of 2a; trivially addable later.)
- A batch "apply everything" button (per-action, matching 2a).

---

## Design

### 1. Read probe + snapshot contract — `backend/app/bridge.py`, `backend/app/contracts.py`

Extend `READ_ONLY_FL_PROBE` with `import channels` and a channels loop using **global
indexing** (`channels.channelCount(True)`, all getters with `useGlobalIndex=True`),
capped at `CHANNEL_PROBE_CAP = 32` (a module constant, mirroring the mixer's 16 cap).
Per channel collect: `index`, `name` (`getChannelName`), `volume` (`getChannelVolume(ci,
False, True)` → normalized 0–1), `pan` (`getChannelPan`), `muted` (`isChannelMuted`),
`solo` (`isChannelSolo`), `selected` (`isChannelSelected`). Add snapshot scalar keys
`channelCount` (`channels.channelCount(True)`) and `selectedChannel`
(`channels.selectedChannel(True, 0, True)`). Every channel read is a pure getter, so the
read-only-probe invariant test (`test_read_only_probe_does_not_include_write_actions`)
keeps passing.

New contract `BridgeChannel` dataclass (mirrors `BridgeMixerTrack`): `index, name,
volume, pan, muted, solo, selected`, with the same validation (`volume` 0–1, `pan`
−1..1, `index ≥ 0`). `BridgeSnapshot` gains `channels: list[BridgeChannel]` (default
`[]`), `channelCount: int | None` (default `None`), and `selectedChannel: int | None`
(default `None`) — **all additive**, so existing snapshots/tests parse unchanged. The
backend snapshot reader gains the two new scalar keys and the channels list, mirroring
how `tracks` is read today.

> Unlike the mixer (whose snapshot carried no mute/solo state, forcing bodyless
> toggles), channels expose `isChannelMuted`/`isChannelSolo`, so the snapshot carries
> real mute/solo state and the UI can light those buttons. The write is still a toggle.

### 2. Write functions — `backend/app/bridge.py`

Each validates inputs (`ValueError` on bad input) and returns `run_bridge_write(...)`.
All use `useGlobalIndex=True`; the name is embedded via `json.dumps` (injection-safe):

- `set_channel(index, *, name=None, volume=None, pan=None)` — validate index via
  `_require_channel_index`; at least one field; `name` non-empty (after strip) and ≤ 100;
  `0 <= volume <= 1`; `-1 <= pan <= 1`. FL code imports `channels` and emits one line per
  provided field: `channels.setChannelName(index, <json>, useGlobalIndex=True)`,
  `channels.setChannelVolume(index, <round4>, useGlobalIndex=True)`,
  `channels.setChannelPan(index, <round4>, useGlobalIndex=True)`. Message summarizes
  changed fields.
- `select_channel(index)` — `channels.selectOneChannel(index, useGlobalIndex=True)`
  (exclusive single-select, the channel analog of mixer `setTrackNumber`).
- `set_channel_mute(index)` — `channels.muteChannel(index, useGlobalIndex=True)` (toggle).
- `set_channel_solo(index)` — `channels.soloChannel(index, useGlobalIndex=True)` (toggle).
- `_require_channel_index(index)` — `0 <= index <= 511` (generous guard; FL enforces real
  existence, and the UI only sends indices the probe surfaced).

### 3. Endpoints — `backend/app/main.py`

Pydantic request model `BridgeChannelRequest` (`name?: str (1–100)`, `volume?: float
(0–1)`, `pan?: float (−1..1)`), each route returning the `BridgeSnapshot` dict:

- `POST /api/bridge/channel/{index}` — `{ name?, volume?, pan? }`
- `POST /api/bridge/channel/{index}/select`
- `POST /api/bridge/channel/{index}/mute`
- `POST /api/bridge/channel/{index}/solo`

`ValueError` from a write function → `HTTPException(400)`, mirroring the mixer endpoints.

### 4. Frontend — `frontend/src/api.js`, `frontend/src/App.jsx`, `frontend/src/styles.css`

- `api.js`: `bridgeSetChannel(index, body)`, `bridgeSelectChannel(index)`,
  `bridgeMuteChannel(index)`, `bridgeSoloChannel(index)`.
- `App.jsx`: a new exported `BridgeChannelControls` component (mirrors
  `BridgeTrackControls`) with name/volume/pan inputs + Apply and Select/Mute/Solo
  buttons; Mute/Solo reflect `channel.muted`/`channel.solo` (lit when active). A new
  **"Channel Rack"** section in `BridgePanel` renders `bridge.channels` (each row: index,
  name, controls). All controls disabled unless `connected` and not `busy`. Handlers wire
  through the existing `runTask`, setting the returned snapshot into state.
- `styles.css`: reuse the existing `.track-controls` styling for the channel rows.

### 5. Error handling

Same as 2a: validation `ValueError` → 400; connection/exec failures return a
`disconnected`/`error` `BridgeSnapshot` whose `message`/`errors` the UI already renders;
the frontend `runTask` try/catch surfaces a 400 via `setMessage`.

### 6. Testing

- **Unit** (`backend/tests/test_bridge.py` style, injected `FakeClient`): per write
  function, assert the exact FL code `exec`'d (with `useGlobalIndex=True`) and that the
  read-only probe re-runs; assert `ValueError` on invalid args (bad index, empty/
  whitespace/>100 name, volume, pan, no-fields); a snapshot round-trip test covering the
  new `channels`/`channelCount`/`selectedChannel`; read-only-probe invariant test still
  green.
- **Endpoint**: each route returns a 200 snapshot via a monkeypatched write function;
  invalid bodies return 422/400.
- **Frontend**: `BridgeChannelControls` test (Select/Mute/Solo fire with the channel
  index; Apply sends only changed fields) + a Channel Rack render test.
- All existing backend/frontend tests stay green.
- **Live acceptance** (user, FL open + scripts enabled): in FL's Channel Rack, rename a
  channel, set its volume/pan, Select/Mute/Solo it — confirm each in FL and that Ctrl+Z
  reverses the edits.

---

## Decisions

- **D1** Reuse `run_bridge_write` unchanged; all channel writes flow through it. The
  read-only probe stays write-free (invariant test preserved).
- **D2** **Global channel indexing** everywhere (read getters and write setters use
  `useGlobalIndex=True`, counts via `channelCount(True)`), so the app and FL agree on
  "channel N" regardless of the Channel Rack group/filter shown in FL.
- **D3** Snapshot fields are additive (`channels`/`channelCount`/`selectedChannel` default
  `[]`/`None`); no existing consumer or test breaks.
- **D4** Mute/Solo are toggles (`muteChannel`/`soloChannel`), but unlike 2a the snapshot
  carries real mute/solo state (`isChannelMuted`/`isChannelSolo`) so buttons reflect it.
- **D5** Volume uses FL's 0–1 channel scale; pan −1..1; name 1–100 chars, `json.dumps`-
  encoded (injection-safe) — matching 2a's validation.
- **D6** Channel count surfaced is capped at `CHANNEL_PROBE_CAP = 32`; the write index
  guard is `0 <= index <= 511` (FL enforces real existence). Exact scale/index behavior
  is confirmed in live acceptance.
- **D7** Every write re-runs the read-only probe and returns a fresh `BridgeSnapshot` so
  the UI (mixer + channels) updates atomically.
- **D8** Branch `phase-2b-live-channel-rack` is cut from master (Phase 0+1+2a already
  merged). Codex reviews the `master..HEAD` diff.

## Rollout / Review

- Implement as small, reviewable commits: read probe + `BridgeChannel` contract →
  `set_channel` (name/vol/pan) → select/mute/solo → endpoints → frontend.
- All existing tests must stay green; live acceptance gates "done".
