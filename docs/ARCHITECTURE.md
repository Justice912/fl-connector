# FL Connector Architecture

Local-first Windows tool for FL Studio 2025. Backend: FastAPI (`backend/app`,
port 8765). Frontend: React/Vite (`frontend/src`, port 5173). All data stays
local under `.data/`.

## Backend modules (`backend/app`)

- `main.py` — FastAPI app, routes, lifespan startup. Holds the singleton
  `PayloadStore`, `ReconstructionStore`, and analysis runner.
- `contracts.py` — frozen dataclasses + validation for notes, payloads, song
  drafts, mastering plans, and bridge snapshots.
- `generator.py` — deterministic prompt-to-notes and prompt-to-song generation,
  dispatched by genre family (amapiano / afro / hiphop).
- `mastering.py` — built-in-FX mixer/master chain plan generation.
- `midi_export.py` — dependency-free Standard MIDI File (type 1) writer for
  one-drag export of songs and single payloads.
- `store.py` — JSON persistence with atomic writes and an append-only event log.
- `paths.py` / `fl_scripts.py` — FL Studio user-data path detection and Piano
  Roll script installation.
- `bridge.py` / `bridge_setup.py` — Flapi live bridge: read-only snapshot,
  transport play/stop, and setup checks.
- `analysis*.py`, `inventory.py`, `reconstruction_*.py` — the Audio-to-FL
  Rebuild pipeline (stem upload, local analysis worker, compilation, export).

## FL Studio integration surfaces

1. **Piano Roll script** — `approve` writes `pending_payload.json`; the installed
   `.pyscript` reads it and calls `flp.score.addNote(...)`. One part at a time.
2. **One-drag MIDI** — `/api/songs/{id}/export-midi` produces a multi-track `.mid`
   the user drags into FL once; each part becomes its own channel/pattern.
3. **Mastering plan** — `approved_mastering_plan.json` plus exact mixer click-paths.
4. **Live bridge (Flapi)** — read-only mixer/transport snapshot + play/stop over
   loopMIDI. Deeper live writes are a later phase.

## Data flow (generate path)

prompt -> `generate_song_draft` -> `PayloadStore.save_song_draft` ->
(approve part -> `pending_payload.json` + Piano Roll script) and/or
(export -> multi-track `.mid` dragged into FL).
