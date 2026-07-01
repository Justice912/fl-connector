# FL Connector

Local Windows-first connector for FL Studio 2025. It turns a natural-language
prompt into approved MIDI-note payloads, then applies the selected payload in
the currently open FL Studio Piano Roll with a companion `.pyscript`.

## What Works Now

- Local FastAPI backend with health, single-part generate, song generate,
  approve, install, and event APIs.
- Deterministic Amapiano prompt-to-notes and prompt-to-song providers for
  offline MVP testing.
- React/Vite web app for prompt entry, piano-roll preview, approval, install,
  grouped song parts, arrangement guide, built-in mastering chain, bridge
  health, and logs.
- Audio-to-FL Rebuild workspace for rights-confirmed stem upload, local analysis
  progress, confidence review, MIDI/audio overrides, Channel Rack and Playlist
  blueprints, sound matching, FL guidance, and reconstruction ZIP export.
- FL Studio Piano Roll writer script that reads the approved payload and calls
  `flp.score.addNote(...)`.
- Secure project storage with ZIP checks, file/count/size limits, checksums,
  local stem preview, correction invalidation, and retryable analysis jobs.
- Tests for the drafting, bridge, reconstruction, export, worker, inventory, and
  frontend review workflows.

## Local Run

Backend:

```powershell
cd "C:\Users\HP\Vocals APP\fl-connector\backend"
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8765
```

Frontend:

```powershell
cd "C:\Users\HP\Vocals APP\fl-connector\frontend"
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Then open `http://127.0.0.1:5173`.

## Deployed Frontend API Base

Local development can leave `VITE_API_BASE` empty because the Vite dev server
proxies `/api` to the local backend. A deployed static frontend must be built
with a browser-reachable API origin:

```powershell
cd "C:\Users\HP\Vocals APP\fl-connector\frontend"
vercel env add VITE_API_BASE production
vercel env add VITE_API_BASE preview
vercel env add VITE_API_BASE development
vercel deploy . -y
```

Use `http://127.0.0.1:8765` when each Vercel prompt asks for the value. For
Preview, leave the Git branch prompt empty unless you want a branch-specific
API base.

When the deployed frontend points at the local backend, start the backend with
the deployed frontend origins in `FL_CONNECTOR_CORS_ORIGINS`:

```powershell
$env:FL_CONNECTOR_CORS_ORIGINS = "https://your-preview.vercel.app,https://your-production-alias.vercel.app"
cd "C:\Users\HP\Vocals APP\fl-connector\backend"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8765
```

Use the hosted API origin instead of `http://127.0.0.1:8765` when the backend is
deployed somewhere reachable from the browser.

## Rebuild A Stem Export

1. Open `Rebuild` in the left navigation.
2. Create a project and confirm that you own the stems or have permission.
3. Upload a ZIP or up to 20 WAV, MP3, FLAC, or M4A files.
4. Complete the local analysis setup shown at the top of the workspace.
5. Click `Analyze locally`, then review tempo, key, confidence, roles, output
   modes, instruments, patterns, Playlist sections, and the built-in mix plan.
6. Approve MIDI patterns one at a time. This reuses the existing FL Connector
   Piano Roll payload and always includes a MIDI backup in the export.
7. Follow the focused FL guide, marking each step complete.
8. Export the reconstruction ZIP from the download icon.

Reconstruction is a faithful, editable interpretation of the uploaded audio.
It does not recover Suno's hidden project, presets, seeds, or original mixer
settings. See [Reconstruction Guide](docs/RECONSTRUCTION.md) for setup,
limits, endpoints, and troubleshooting.

## FL Studio Apply Flow

1. In the web app, click `Install Script`.
2. Click `Generate Song Draft`.
3. Select a part such as `FPC bounce drums`, `Deep sub bass pulse`, or
   `Main log drum riff`.
4. Click `Approve Selected Part`.
5. In FL Studio, open the matching instrument's Piano Roll:
   `Channel Rack > click instrument > Piano Roll` or press `F7`.
6. Run:
   `Piano Roll menu > Tools > Scripts > FL Connector Apply Payload`.
7. Repeat steps 3-6 for each part you want to place in FL Studio.
8. Press play in FL Studio to hear the notes.

## FL Studio Built-In Mastering Flow

1. After generating a song draft, click `Generate Master Chain`.
2. Review the generated built-in plugin steps.
3. Click `Approve Master Chain`.
4. Open the Mixer in FL Studio with `F9`.
5. Follow the chain in the app, adding each listed plugin to the matching mixer
   track and slot.

The current Phase 3 chain uses only built-in FL Studio effects such as:

- `Fruity Parametric EQ 2`
- `Fruity Compressor`
- `Fruity Stereo Shaper`
- `Fruity Reverb 2`
- `Fruity Delay 3`
- `Maximus`
- `Fruity Limiter`

Approval writes the machine-readable plan to:

```text
C:\Users\HP\Documents\Image-Line\FL Studio\Settings\Piano roll scripts\FL Connector\approved_mastering_plan.json
```

That file is intended for the later live mixer bridge. Today, the verified
Phase 3 behavior is plan generation, approval, persistence, and exact FL Mixer
click-path guidance.

## Live FL Bridge Health

Phase 4 has started with a read-only bridge health slice:

- `GET /api/bridge/health` returns a `BridgeSnapshot`.
- `POST /api/bridge/transport` accepts `play` or `stop` for the first safe
  live control slice.
- The React app shows live bridge status, setup steps, and read-only mixer or
  transport data when Flapi responds, plus Play/Stop transport buttons once
  the bridge is connected.
- The Vite dev server proxies `/api` to `http://127.0.0.1:8765`, so local
  browser testing can use same-origin API calls.

The bridge health probe is read-only. Phase 5 adds only reversible transport
Play/Stop actions. It does not select tracks, insert plugins, record, or change
mixer values.

To make the bridge connect, install/configure Flapi separately:

1. Install the Flapi Python package in the backend environment.
2. Create loopMIDI ports named `Flapi Request` and `Flapi Response`.
3. Enable the Flapi controller scripts in FL Studio MIDI settings.
4. Restart FL Studio and refresh the bridge panel.

The Phase 2 generator currently creates five Amapiano parts:

- `FPC bounce drums`
- `Deep sub bass pulse`
- `FLEX warm pad chords`
- `Main log drum riff`
- `Sparse top response`

## Run as a desktop app (Windows)

One-time setup: `cd frontend && npm run build`, then
`backend\.venv\Scripts\python -m pip install "pywebview>=5,<6"`.

Then double-click **Start FL Connector.cmd** (or run
`scripts/install-shortcut.ps1` once to add a Desktop icon). FL Connector opens in
its own window with the backend running locally. FL Studio + Flapi and the
on-demand analysis worker are unchanged.

## Reference Repos

- `.scratch/external/Flapi` is the live-bridge reference fork candidate.
- `.scratch/external/NFXTemplate` is the FL Studio MIDI script scaffold reference.

Those repos are not app dependencies yet. This MVP keeps the first note-writing
path reliable by using FL Studio's official Piano Roll scripting surface.
