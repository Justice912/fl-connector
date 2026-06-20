# FL Connector MVP Notes

## Goal

The MVP proves the smallest useful loop and the Phase 2 grouped-song extension:

```text
Prompt -> MIDI note payload -> user approval -> FL Piano Roll script -> notes in FL Studio
Prompt -> grouped song draft -> selected part -> approval -> FL Piano Roll script
Prompt/song draft -> built-in mastering chain -> approval -> Mixer F9 guide
Flapi bridge probe -> read-only bridge snapshot -> UI health panel
Flapi transport action -> play/stop -> fresh bridge snapshot
```

The live bridge and MCP-style control layer can grow from the same backend once
we start using the Flapi reference in `.scratch/external/Flapi`.

## Why The Hybrid Apply Path

FL Studio exposes reliable note creation through Piano Roll scripts via
`flp.score.addNote(...)`. The MIDI controller scripting surface is better for
live transport/session/controller integration, but it is not the same context as
the Piano Roll score API.

For that reason, the MVP writes an approved JSON payload to the user's FL Studio
settings folder and installs a small `.pyscript` that applies the notes inside
the currently open Piano Roll.

## Phase 2 Song Drafting

`POST /api/songs/generate` creates a grouped `SongDraft` with FL-applicable
parts. Each part wraps a normal `NotePayload`, so the existing approval and
Piano Roll writer path remains unchanged.

The first full-draft template is Amapiano:

- Drums: FPC bounce guide with kick, clap, hats, open hat, and shaker notes.
- Bass: deep 3xOsc/BooBass-style pulse.
- Chords: FLEX warm pad chords.
- Log drum: main melodic log drum riff.
- Melody: sparse top response.

The UI shows apply order, plugin hints, note counts, and an arrangement strip.
The user still opens the matching FL Studio instrument Piano Roll and applies
one approved part at a time.

## Phase 3 Built-In Mastering

`POST /api/mastering/generate` creates a `MasteringPlan` made of ordered
`MixStep` items. Each step names:

- target mixer track role,
- built-in FL Studio effect plugin,
- suggested slot number,
- plain-English action,
- starting settings,
- exact `F9` Mixer click path.

`POST /api/mastering/{id}/approve` marks the plan approved and writes it to the
FL Connector data folder as `approved_mastering_plan.json`.

This phase does not claim automatic mixer plugin insertion. Local evidence shows
FL controller scripts can inspect mixer/plugin state, but a safe plugin-chain
insertion path is not yet implemented. The approved JSON file is the bridgeable
contract for that future automation.

## Phase 4 Read-Only Bridge Health

`GET /api/bridge/health` now exposes a `BridgeSnapshot` contract for the first
live-bridge slice. The backend attempts to connect through Flapi, runs a
read-only probe, and returns:

- FL version and project title when available.
- transport state such as playing, recording, loop mode, position, length, and
  tempo.
- mixer track count, selected track, visible track names, volume, pan, selected
  state, and existing plugin slot names.
- setup steps and errors when Flapi is missing or disconnected.

The frontend shows this state in the Live FL bridge panel. The Vite dev server
proxies `/api` to `http://127.0.0.1:8765`, so browser testing uses same-origin
requests by default.

The probe is deliberately read-only. It does not call FL write functions such as
transport start/stop, track selection, mixer setters, or plugin parameter
setters. Live write automation remains a future phase after a real connected
Flapi session is verified.

## Phase 5 Live Transport Control

After the read-only bridge connected successfully, the first live write slice is
limited to reversible transport control:

- `POST /api/bridge/transport` accepts `play` and `stop`.
- The backend sends only `transport.start()` or `transport.stop()` through
  Flapi.
- The backend immediately returns a fresh `BridgeSnapshot`.
- The frontend shows Play and Stop buttons only when the bridge is connected.

This phase still does not claim automatic mixer-chain insertion, track
selection, recording, plugin insertion, or note writing through the Flapi
controller bridge.

## Current Boundaries

- Windows + FL Studio 2025 first.
- Built-in FL Studio plugins only for later mixing/mastering.
- Amapiano note and grouped-song generation first.
- Mastering uses FL Studio built-in effects only.
- Live bridge control is limited to bridge health plus play/stop transport
  actions, and depends on external Flapi/loopMIDI setup.
- No blocked vocal-generation/TCSinger2 work is wired into this connector.
- The AI provider is currently deterministic/mockable; cloud providers can be
  added behind the same payload schema.
