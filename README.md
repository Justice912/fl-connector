# FL Connector MVP

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
- FL Studio Piano Roll writer script that reads the approved payload and calls
  `flp.score.addNote(...)`.
- Tests for payload validation, song-part generation, deterministic generation,
  mastering-chain generation, read-only bridge schema, and FL path detection.

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

## Reference Repos

- `.scratch/external/Flapi` is the live-bridge reference fork candidate.
- `.scratch/external/NFXTemplate` is the FL Studio MIDI script scaffold reference.

Those repos are not app dependencies yet. This MVP keeps the first note-writing
path reliable by using FL Studio's official Piano Roll scripting surface.
