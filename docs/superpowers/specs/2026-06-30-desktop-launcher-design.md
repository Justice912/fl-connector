# FL Connector Desktop Launcher (Design)

Date: 2026-06-30
Status: Approved (brainstorming) — ready for implementation planning

## Context

FL Connector is an inherently **local** tool: the FastAPI backend (`backend/.venv`,
uvicorn on `127.0.0.1:8765`) must run on the same machine as FL Studio because it reads/writes
FL's local files (Piano Roll scripts, `Documents\Image-Line\...`), talks to a running FL via the
Flapi MIDI bridge (loopMIDI + controller scripts), runs stem analysis (librosa/basic_pitch) on
local files, and scans installed plugins/samples. A cloud/hosted frontend (Vercel) is only a UI
shell — it cannot reach the local backend (HTTPS→HTTP mixed content) and could not touch FL
anyway.

Today, using the tool means running two terminal commands (backend uvicorn + frontend Vite) and
opening a browser. This is friction for the user (a producer) and is the source of the recurring
"the app looks old / no bridge" confusion (stale hosted build).

A desktop launcher removes that friction: one double-click opens FL Connector in its own window
with the backend already running.

## Goal

Double-clicking one icon starts the backend and opens FL Connector in a **native desktop window**
on this machine, reusing the existing `backend/.venv`. No browser, no two-terminal dance, no
hosted-URL confusion.

## Scope (confirmed during brainstorming)

- **Target:** this machine only — a launcher that reuses the existing Python/venv. **Not** a
  standalone installer for other PCs (deferred as a possible later stage).
- **Window:** a native app window via **pywebview** (uses the Windows built-in WebView2/Edge
  runtime; nothing Chromium to bundle).
- **Window type confirmed** over "open in default browser."
- FL Studio + Flapi remain external/unchanged. The heavy ML **analysis worker stays the existing
  on-demand winget install** (`.analysis-worker/`); it is **not** bundled.
- Resolved sub-decisions: **include** the optional Desktop shortcut/icon script; the static mount
  is **auto-enabled whenever `frontend/dist` exists** (so even a plain `uvicorn` run serves the UI).

## Architecture

**One Python process, one window.** The launcher starts `uvicorn` (the existing `backend/.venv`)
bound to `127.0.0.1:8765`. That single server serves **both**:

- the API at `/api/*` (and `/docs`, `/openapi.json`) — unchanged, and
- the **built frontend** (`frontend/dist`) at `/`.

A **pywebview** window titled "FL Connector" loads `http://127.0.0.1:8765`. Because everything is
one origin over `http://127.0.0.1`, there is no mixed-content problem and the SPA's existing
relative `/api` calls work without any `VITE_API_BASE`.

```
[ Start FL Connector.cmd ] → backend/.venv python desktop.py
        │
        ├─ if backend already up on :8765 → reuse it
        ├─ else start uvicorn(app) in a daemon thread, wait for /api/health
        └─ open pywebview window → http://127.0.0.1:8765
                                        │
              FastAPI: /api/* (existing)  +  StaticFiles(frontend/dist) at /
```

## Components

### 1. `backend/app/static_site.py` (new)
- `mount_frontend(app, dist_dir: Path) -> bool`: if `dist_dir/index.html` exists, mounts
  `StaticFiles(directory=dist_dir, html=True)` at `/` and returns `True`; otherwise returns
  `False` (no-op).
- Called from `main.py` **after all routers/routes are registered**, guarded by the existence of
  `frontend/dist/index.html`, so `/api/*` and FastAPI built-ins always resolve first and dev/test/CI
  without a build are unaffected.
- The app uses tab state (no client-side deep-link routing), so `html=True` serving `index.html`
  at `/` plus hashed assets is sufficient — no custom SPA catch-all fallback needed.

### 2. `desktop.py` (new, repo root)
Launcher entrypoint, run by `backend/.venv`'s Python. Responsibilities, with the testable logic
split from the UI call:
- `frontend_dist() -> Path`: resolves `<repo>/frontend/dist`.
- `backend_is_up(url: str, timeout: float) -> bool`: returns True if `GET {url}/api/health` responds OK.
- Decision: if `backend_is_up` → reuse (just open the window). Else start `uvicorn.Server` in a
  daemon thread on `127.0.0.1:8765`, poll `backend_is_up` until ready (bounded timeout), then open
  the window.
- `webview.create_window("FL Connector", url)` + `webview.start()`; on window close, signal the
  uvicorn server to stop and exit.
- If `dist` is missing, print a clear instruction to run `npm run build` and exit non-zero.

### 3. `Start FL Connector.cmd` (new, repo root)
Double-click entry: `backend\.venv\Scripts\python desktop.py` (with the correct working directory),
so the user never opens a terminal.

### 4. `scripts/install-shortcut.ps1` (new, optional one-time)
Creates a Desktop `.lnk` pointing at `Start FL Connector.cmd` with an icon, giving a real
app icon to launch from.

### 5. Dependency
Add `pywebview` to `backend/requirements.txt` and install it into `backend/.venv` (currently not
installed). WebView2 runtime is already present on Windows 11.

## Data flow

Window → `http://127.0.0.1:8765` → FastAPI serves `index.html` + hashed assets from
`frontend/dist`; the SPA issues relative `/api/*` requests to the same origin. Generate, Bridge,
Analyze, and Send-to-FL behave exactly as they do today.

## First run / build

One-time setup: install `pywebview` into `backend/.venv` and run `npm run build` (produces
`frontend/dist`). The launcher then assumes `dist` exists. (The `dist` already produced during the
Phase 4 preview satisfies this.)

## Error handling

- **Port in use:** if `:8765` already answers `/api/health`, reuse that instance (open the window
  at it) instead of failing.
- **Server start timeout:** bounded wait for `/api/health`; on timeout, show a clear error and exit.
- **Missing `dist`:** friendly "run `npm run build`" message, non-zero exit.
- **Window close:** cleanly stop the uvicorn thread.

## Testing

- **`static_site`** (`backend/tests/`): serving `index.html` at `/` (200, `text/html`), an asset
  resolves, `/api/health` still wins over the mount, and `mount_frontend` is a no-op returning
  `False` when `dist`/`index.html` is absent. Use a temp `dist` dir so existing **158** backend
  tests stay green regardless of whether a real build is present.
- **`desktop` helpers** (`backend/tests/` or a root test): `backend_is_up` against a fake/mock URL
  (up vs refused), `frontend_dist()` resolution, and the start-vs-reuse decision as pure unit
  tests. The `webview.create_window`/`start()` calls are isolated in a thin `main()` and are **not**
  unit-tested (UI surface).

## Out of scope (deliberate)

- Standalone installer / PyInstaller-bundled Python for machines without Python (possible later stage).
- Code signing, auto-update.
- Bundling the ML analysis worker (stays on-demand winget install).
- Any change to FL/Flapi integration, generation, or reconstruction behavior.

## Acceptance (user-run, after build)

1. Run `Start FL Connector.cmd` (or the Desktop shortcut) → a native "FL Connector" window opens
   showing the app, with no terminal and no browser.
2. The Draft and Rebuild tabs work; `/api/health` is green; Generate produces a draft — i.e. the
   backend is live inside the window.
3. Closing the window stops the backend (no orphaned `python.exe` on `:8765`).
4. Launching again while one instance is already running reuses it rather than erroring.
