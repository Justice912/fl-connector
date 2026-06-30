# Phase 4 — Close the FL Loop for Rebuild (Design)

Date: 2026-06-30
Status: Approved (brainstorming) — ready for implementation planning

## Context

The Rebuild (audio reconstruction) feature already runs end-to-end: create project →
upload owned stems → local analysis (`analysis_worker`: librosa tempo/key/drums +
`basic_pitch` pitched transcription) → review/correct → blueprint (channel-rack plan with
mini piano rolls) → arrangement timeline → sound recommendations → mix plan → FL guide
carousel → export ZIP.

The handoff into FL Studio is the weak link. Today the reconstruction export produces a
**ZIP of many separate per-pattern `.mid` files** plus JSON metadata and a manual,
step-by-step guide. The user (a producer) must unpack and place each file by hand. The
generator side, by contrast, already has the seamless Phase 1 path
(`GET /api/songs/{id}/export-midi` → one multi-track `.mid` you drag in once).

Phase 4 closes the loop: give Rebuild the same one-drag spine, and use the Phase 2 Flapi
bridge to scaffold the FL session to match.

## Goal

A producer finishes a reconstruction and, with **one MIDI drag plus one Sync click**, lands
all reconstructed parts on their own tracks at the correct bar positions in an FL session
whose tempo and channel/mixer-track names already match the rebuild.

## Hard platform constraints (honest)

These come from FL's MIDI Controller scripting API (what Flapi taps) and are non-negotiable:

- **Notes can only enter FL via a MIDI drag.** Flapi cannot place notes.
- **Flapi cannot create channels or mixer tracks**, and cannot insert plugins. It can only
  set properties of **existing** channels/mixer tracks by index (name, volume, pan,
  mute/solo/select) and set transport/tempo.
- Therefore the Flapi "scaffold" is a **post-drag sync**: dragging the multi-track MIDI is
  what creates the channels (one per note-bearing track, in track order); the sync then
  renames those now-existing channels/tracks and sets tempo.
- **The mix plan carries no numeric volume/pan values** — its steps are textual EQ / Maximus
  / Limiter instructions. The sync will **not fabricate** mixer levels. It sets tempo and
  names only (both fully backed by real data); the mix plan stays as the guided checklist.

## Chosen approach

- **Handoff shape:** multi-track MIDI **and** Flapi scaffold (the fullest loop).
- **Sync implementation:** **Approach A — server-side orchestrator.** A pure planning
  function + a `/sync-fl` endpoint that applies the plan via the existing, already-verified
  bridge writes and returns a per-action report. Chosen over client-side orchestration
  (Approach B) to keep business logic in a Python-tested pure module — matching the project's
  established pattern (`groove.py`, `harmony.py`, `fills.py`) — and over A+dry-run (Approach
  C) because the apply-report already tells the user what changed vs. what they must create.

## Components

### 1. Multi-track MIDI export (the spine)

Add a pure function `reconstruction_to_midi(project: ReconstructionProject) -> bytes` to
`backend/app/midi_export.py`, reusing that module's existing tested helpers
(`_conductor_track`, `_encode_track`, `_note_events`, `_header`; PPQ 96; Format-1) so all
MIDI byte-encoding stays in one module and matches the generator output.

- **Conductor track:** title = `project.title`; tempo = `round(analysisSummary.bpm)`; 4/4.
- **One track per MIDI part** (`part.outputMode == "midi"`), named `part.name`,
  channel = `partIndex % 16` (mirrors `song_to_midi`).
- For each part, flatten its `PatternSlice`s into one absolute-position `list[Note]`: for
  every placement bar `b` in `pattern.placements`, each note becomes
  `startBeats + (b - 1) * 4` (one beat = one quarter; 4 beats/bar). Pass the flattened list
  to `_note_events`. This yields the full-length arrangement from a single drag.
- **Audio parts excluded** (cannot enter via MIDI; remain aligned-audio references).
- **Endpoint** `GET /api/reconstructions/{id}/export-midi` → `Response(media_type="audio/midi",
  Content-Disposition: attachment)`, mirroring `export_song_midi`. Errors:
  `404` unknown project; `400` if the project has zero MIDI parts (nothing to send).

### 2. Server-side sync orchestrator

New module `backend/app/reconstruction_sync.py`.

- **Pure** `build_sync_plan(project, snapshot)`:
  - Inputs: the project and a live bridge snapshot (`channelCount`, `trackCount`, and the
    existing `channels`/`mixer` arrays from `probe_bridge`).
  - Produces a plan:
    - `tempo`: `round(analysisSummary.bpm)` (or `None` if no summary).
    - `channels`: MIDI parts in order mapped to channel indices `0..channelCount-1`,
      each `{index, name=part.name}`.
    - `mixer`: MIDI parts in order mapped to mixer inserts `1..trackCount`,
      each `{index, name=part.name}`.
    - `skipped`: parts beyond the live channel/track counts, with a human message
      (e.g. "Create 2 more channels in FL, then sync again").
  - No I/O; deterministic; unit-tested directly.
- **Endpoint** `POST /api/reconstructions/{id}/sync-fl`:
  - Probes the bridge (existing `probe_bridge`). If disconnected → return `200` with a clear
    "FL/Flapi not connected" report (mirrors existing bridge endpoints; never a 500).
  - Builds the plan, applies each item via the **existing** verified bridge writes
    (`set_project_tempo`, `set_channel(index, name=…)`, `set_mixer_track(index, name=…)`),
    best-effort / continue-on-error.
  - Returns a `SyncReport` dict:
    `{ "connected": bool, "tempo": {value, status}, "channels": [{index, name, status}],
       "mixer": [{index, name, status}], "skipped": [{kind, message}], "message": str }`.
  - `404` on unknown project.
- The pure/I-O split mirrors `bridge.py`: planning is pure and unit-tested; the endpoint does
  probe + apply and is tested with a fake bridge client (as existing bridge tests do).

### 3. Frontend "Send to FL"

In `frontend/src/reconstruction/ReconstructionWorkspace.jsx`, add a **Send to FL** card
(replacing the lone export icon in the top bar; the ZIP export stays available):

- **Download arrangement MIDI** → calls `exportReconstructionMidi(projectId)`, triggers the
  browser download. Copy: "Drag this one file into the FL Playlist."
- **Sync FL to this rebuild** → calls `syncReconstructionToFl(projectId)`, renders the report
  (tempo set · N channels named · M mixer tracks named · "create K more channels"). Reflects
  live bridge connection status; disabled with a hint when disconnected.
- **ZIP export** retained (full bundle: audio + JSON + guide). The ZIP additionally embeds the
  new spine as `arrangement.mid`.

Two new `frontend/src/api.js` methods: `exportReconstructionMidi`, `syncReconstructionToFl`.

### 4. Updated guide steps

Rewrite `_guide_steps()` in `backend/app/reconstruction_compiler.py` to the real loop
(guide is data-driven, so the frontend carousel updates automatically):

1. Download & drag the **arrangement MIDI** into the Playlist (notes land on per-part tracks).
2. Click **Sync FL to this rebuild** (sets tempo + names the channels/mixer tracks).
3. Add the approved instrument per channel + insert plugins (**manual** — Flapi can't).
4. Apply the mix plan (built-in FL EQ / Maximus / Limiter, as today).
5. Check the arrangement sections.

## Data flow

```
reconstruction project (parts + patterns + analysisSummary + mixPlan)
        │
        ├── GET /export-midi → reconstruction_to_midi() → single multi-track .mid
        │                                                   → user drags into FL (channels created)
        │
        └── POST /sync-fl → probe_bridge() → build_sync_plan(project, snapshot)
                                                   → apply via set_project_tempo / set_channel /
                                                     set_mixer_track → SyncReport → UI
```

## Error handling

- `export-midi`: `404` unknown project; `400` no MIDI parts.
- `sync-fl`: `404` unknown project; bridge disconnected → `200` with a disconnected report;
  per-action failures captured in the report (status per item), never crash the whole sync.

## Testing

- **`reconstruction_to_midi`**: track count = conductor + MIDI parts; tempo meta matches
  BPM; notes placed at absolute positions (placement offset applied); audio parts excluded;
  deterministic bytes for fixed input. Endpoint `400` (no MIDI parts) / `404` paths.
- **`reconstruction_sync`**: pure `build_sync_plan` — part→channel and part→mixer mapping,
  skip entries when counts are short, tempo value, empty/None summary handling. Endpoint with
  a fake bridge client — applies the expected writes, returns the report, handles
  disconnected.
- **Frontend** (`ReconstructionWorkspace.test.jsx`): Send-to-FL card renders; download button
  calls the export method; sync button calls the client and renders the report; sync disabled
  when the bridge is disconnected.

## Out of scope (deliberate)

- Analysis-accuracy work (faked timeline sections, crude 3-class drum transcription, tempo/key
  precision) — that was the alternative Phase 4 direction and is not part of this loop.
- The project status state machine (no new statuses; "Send to FL" is an action).
- Audio-part automation (aligned audio stays a manual/guide concern).
- Auto-applying numeric mixer levels (the mix plan has none; not fabricating them).

## Live-FL acceptance (user-run, after build)

1. Generate a reconstruction, download the arrangement MIDI, drag into FL → verify one track
   per MIDI part at correct bars, full length.
2. With FL + Flapi live, click **Sync FL to this rebuild** → verify tempo moves to the detected
   BPM, channels and mixer tracks are renamed to the part names in order, and the report lists
   any "create K more channels" correctly.
3. Confirm the part *i* ↔ channel *i* ordering assumption holds after a MIDI drag (the one
   ordering risk noted above).
