# FL Connector Desktop Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One double-click opens FL Connector in a native desktop window on this machine, with the local backend started automatically and serving the built frontend.

**Architecture:** The existing FastAPI app gains a static mount so a single `uvicorn` on `127.0.0.1:8765` serves both `/api/*` and the built `frontend/dist`. A thin repo-root `desktop.py` starts (or reuses) that server and opens a **pywebview** native window at it. All testable logic lives in the `app` package; `desktop.py` is thin glue with a headless `--check` path.

**Tech Stack:** Python 3, FastAPI/Starlette `StaticFiles`, `uvicorn` (programmatic `Server`), `pywebview` (Windows WebView2), pytest.

## Global Constraints

- **This-machine launcher only.** Reuse the existing `backend/.venv`. No PyInstaller / bundled Python / installer (out of scope).
- Native window via **pywebview**, **lazy-imported** only on the real launch path (so tests and `--check` never need it). WebView2 runtime is already present on Windows 11.
- One server serves **both** `/api/*` and the built frontend; single origin `http://127.0.0.1:8765`. The SPA already uses relative `/api` paths — do not introduce `VITE_API_BASE`.
- The static mount is **auto-enabled only when `frontend/dist/index.html` exists**, and mounted **after all API routes** so `/api/*`, `/docs`, `/openapi.json` always win.
- `pywebview` is added to `backend/requirements.txt` and installed into `backend/.venv` (currently not installed).
- **Pure/testable logic lives in the `app` package** (`static_site.py`, `desktop_support.py`); `desktop.py` (repo root) is a thin, non-unit-tested launcher with a `--check` headless verification path.
- `APP_ROOT` in `backend/app/main.py` is `Path(__file__).resolve().parents[2]` = the repo root; the build dir is `APP_ROOT / "frontend" / "dist"`.
- Existing **158** backend tests must stay green. FL/Flapi and the on-demand analysis worker are unchanged.
- Run pytest from `backend/`: `cd backend && python -m pytest ...`.

---

### Task 1: Serve the built frontend (`static_site.mount_frontend`)

**Files:**
- Create: `backend/app/static_site.py`
- Modify: `backend/app/main.py` (one import near the other `from .` imports; one call appended at end of file)
- Test: `backend/tests/test_static_site.py`

**Interfaces:**
- Consumes: `fastapi.FastAPI`, `fastapi.staticfiles.StaticFiles`.
- Produces: `mount_frontend(app: FastAPI, dist_dir: Path) -> bool` — mounts `StaticFiles(html=True)` at `/` when `dist_dir/index.html` exists (returns `True`), else no-op (`False`).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_static_site.py`:

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.static_site import mount_frontend


def _make_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><title>FL Connector</title>", encoding="utf-8"
    )
    (dist / "assets" / "app.js").write_text("console.log('app')", encoding="utf-8")
    return dist


def test_mount_frontend_serves_index_and_assets(tmp_path):
    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"ok": True}

    mounted = mount_frontend(app, _make_dist(tmp_path))
    client = TestClient(app)

    assert mounted is True
    root = client.get("/")
    assert root.status_code == 200
    assert "FL Connector" in root.text
    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert "console.log" in asset.text
    # API still wins over the catch-all static mount
    assert client.get("/api/health").json() == {"ok": True}


def test_mount_frontend_is_noop_without_build(tmp_path):
    app = FastAPI()
    mounted = mount_frontend(app, tmp_path / "missing-dist")
    assert mounted is False
    assert TestClient(app).get("/").status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_static_site.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.static_site'`.

- [ ] **Step 3: Implement `static_site.py`**

Create `backend/app/static_site.py`:

```python
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def mount_frontend(app: FastAPI, dist_dir: Path) -> bool:
    """Serve the built frontend at / when a production build exists.

    Returns True when the static files were mounted, False when there is no
    build (so dev/test/CI without `npm run build` are unaffected). Must be
    called AFTER all API routes are registered so /api/* and the FastAPI
    built-ins resolve before this catch-all mount.
    """
    index = Path(dist_dir) / "index.html"
    if not index.is_file():
        return False
    app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_static_site.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Wire into `main.py`**

In `backend/app/main.py`, add this import alongside the other `from .` imports (e.g. after `from .reconstruction_sync import apply_reconstruction_sync`):

```python
from .static_site import mount_frontend
```

Then append this as the **last line** of `backend/app/main.py` (after every route is defined):

```python
mount_frontend(app, APP_ROOT / "frontend" / "dist")
```

- [ ] **Step 6: Run the full backend suite (regression)**

Run: `cd backend && python -m pytest -q`
Expected: PASS — previously 158, now 160 (the 2 new tests). The static mount at `/` must not shadow any existing route.

- [ ] **Step 7: Commit**

```bash
git add backend/app/static_site.py backend/app/main.py backend/tests/test_static_site.py
git commit -m "feat: serve built frontend from the backend when present"
```

---

### Task 2: Launcher helpers (`desktop_support`) + pywebview dependency

**Files:**
- Create: `backend/app/desktop_support.py`
- Modify: `backend/requirements.txt` (add `pywebview`)
- Test: `backend/tests/test_desktop_support.py`

**Interfaces:**
- Produces:
  - `frontend_dist(app_root: Path) -> Path` → `app_root / "frontend" / "dist"`.
  - `backend_is_up(base_url: str, timeout: float = 1.0) -> bool` → `True` iff `GET {base_url}/api/health` returns HTTP 200.
- Consumes (Task 3): both helpers.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_desktop_support.py`:

```python
from app.desktop_support import backend_is_up, frontend_dist


def test_frontend_dist_resolves_under_app_root(tmp_path):
    assert frontend_dist(tmp_path) == tmp_path / "frontend" / "dist"


def test_backend_is_up_false_when_nothing_listening():
    # Port 9 (discard) is effectively never open for HTTP here -> refused -> False.
    assert backend_is_up("http://127.0.0.1:9", timeout=0.5) is False


def test_backend_is_up_true_against_a_live_health_endpoint():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/health":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok": true}')
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert backend_is_up(f"http://127.0.0.1:{port}", timeout=2.0) is True
    finally:
        server.shutdown()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_desktop_support.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.desktop_support'`.

- [ ] **Step 3: Implement `desktop_support.py`**

Create `backend/app/desktop_support.py`:

```python
from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path


def frontend_dist(app_root: Path) -> Path:
    return Path(app_root) / "frontend" / "dist"


def backend_is_up(base_url: str, timeout: float = 1.0) -> bool:
    """True if {base_url}/api/health responds with HTTP 200."""
    url = base_url.rstrip("/") + "/api/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_desktop_support.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Add the pywebview dependency and install it**

Append to `backend/requirements.txt`:

```
pywebview>=5,<6
```

Install into the existing venv:

Run: `backend/.venv/Scripts/python -m pip install "pywebview>=5,<6"`
Expected: installs pywebview (and its Windows WebView2 binding) successfully.

Then verify the import works:

Run: `backend/.venv/Scripts/python -c "import webview; print('pywebview', webview.__version__)"`
Expected: prints `pywebview 5.x`. (If install fails, STOP and report — do not proceed.)

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && python -m pytest -q`
Expected: PASS — now 163 (3 new tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app/desktop_support.py backend/tests/test_desktop_support.py backend/requirements.txt
git commit -m "feat: add desktop launcher helpers and pywebview dependency"
```

---

### Task 3: Launcher entrypoint + double-click + shortcut

**Files:**
- Create: `desktop.py` (repo root)
- Create: `Start FL Connector.cmd` (repo root)
- Create: `scripts/install-shortcut.ps1`
- Modify: `README.md` (add a short "Run as a desktop app" note)

**Interfaces:**
- Consumes: `app.desktop_support.frontend_dist`, `app.desktop_support.backend_is_up` (Task 2); `app.main:app` and `uvicorn`; `webview` (lazy, real-launch only).
- Produces: a runnable launcher. `python desktop.py --check` starts/reuses the backend, confirms `/api/health`, and exits 0 **without** opening a window (headless verification). `python desktop.py` opens the native window.

- [ ] **Step 1: Create the launcher**

Create `desktop.py` at the repo root:

```python
"""FL Connector desktop launcher (this machine).

Double-click `Start FL Connector.cmd`, or run:
    backend/.venv/Scripts/python desktop.py

Starts the local backend (or reuses one already running) and opens FL Connector
in a native window. Pass --check to verify the launch path without a window.
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8765
URL = f"http://{HOST}:{PORT}"

# Make the backend package importable when run from the repo root.
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.desktop_support import backend_is_up, frontend_dist  # noqa: E402


def _start_server():
    import uvicorn
    from app.main import app

    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    return server


def _wait_until_up(timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if backend_is_up(URL, timeout=1.0):
            return True
        time.sleep(0.3)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FL Connector desktop launcher")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the launch path (start/reuse + health) without opening a window",
    )
    args = parser.parse_args(argv)

    if not (frontend_dist(REPO_ROOT) / "index.html").is_file():
        print("Frontend build missing. Run: cd frontend && npm run build", file=sys.stderr)
        return 1

    server = None
    if backend_is_up(URL, timeout=1.0):
        print(f"Reusing FL Connector backend already running at {URL}")
    else:
        server = _start_server()
        if not _wait_until_up():
            print("Backend did not become ready in time.", file=sys.stderr)
            return 1
        print(f"FL Connector backend ready at {URL}")

    if args.check:
        if server is not None:
            server.should_exit = True
        return 0

    import webview

    webview.create_window("FL Connector", URL, width=1440, height=900)
    webview.start()
    if server is not None:
        server.should_exit = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Create the double-click entry**

Create `Start FL Connector.cmd` at the repo root (note: `%~dp0` ends with a backslash):

```bat
@echo off
cd /d "%~dp0"
"%~dp0backend\.venv\Scripts\python.exe" "%~dp0desktop.py"
```

- [ ] **Step 3: Create the optional Desktop shortcut script**

Create `scripts/install-shortcut.ps1`:

```powershell
# Creates a Desktop shortcut that launches FL Connector.
$root = Split-Path -Parent $PSScriptRoot
$target = Join-Path $root 'Start FL Connector.cmd'
$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = Join-Path $desktop 'FL Connector.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($lnk)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $root
$shortcut.WindowStyle = 7  # launch minimized (no lingering console)
$shortcut.Description = 'FL Connector desktop'
$shortcut.Save()
Write-Host "Created shortcut: $lnk"
```

- [ ] **Step 4: Document the launch method**

Add this section to `README.md` (near the existing run instructions; if none, append at the end):

```markdown
## Run as a desktop app (Windows)

One-time setup: `cd frontend && npm run build`, then
`backend\.venv\Scripts\python -m pip install "pywebview>=5,<6"`.

Then double-click **Start FL Connector.cmd** (or run
`scripts/install-shortcut.ps1` once to add a Desktop icon). FL Connector opens in
its own window with the backend running locally. FL Studio + Flapi and the
on-demand analysis worker are unchanged.
```

- [ ] **Step 5: Verify the launch path headlessly (`--check`)**

Ensure the frontend is built (`frontend/dist/index.html` exists; run `cd frontend && npm run build` if needed). Then:

Run: `backend/.venv/Scripts/python desktop.py --check`
Expected: exit code 0, printing either `FL Connector backend ready at http://127.0.0.1:8765` (started its own) or `Reusing FL Connector backend already running at http://127.0.0.1:8765` (an instance was already up). Confirm exit 0:

Run: `echo $?` (bash) — Expected: `0`.

Also confirm the launcher parses/imports cleanly:

Run: `backend/.venv/Scripts/python -c "import ast; ast.parse(open('desktop.py').read()); print('ok')"`
Expected: `ok`.

- [ ] **Step 6: Commit**

```bash
git add desktop.py "Start FL Connector.cmd" scripts/install-shortcut.ps1 README.md
git commit -m "feat: add desktop launcher entrypoint, double-click, and shortcut"
```

---

### Task 4: Manual acceptance (user-run)

**Files:** none (verification only — requires a desktop session for the GUI window).

- [ ] **Step 1: Launch via double-click**

Double-click `Start FL Connector.cmd` (or the Desktop shortcut). Expect a native **FL Connector** window (no browser, no visible terminal) showing the app.

- [ ] **Step 2: Confirm the backend is live in-window**

In the window, the Draft and Rebuild tabs render; trigger a Generate to confirm `/api/*` works from inside the window.

- [ ] **Step 3: Confirm clean shutdown and reuse**

Close the window → no orphaned `python.exe` holding `:8765`. Launch again while one instance is already running → it reuses the running instance rather than erroring.

---

## Self-Review

**Spec coverage:**
- Native window via pywebview, this-machine, reuse venv → Task 3 (`desktop.py`) + Task 2 (dependency). ✓
- Backend serves `/api/*` + built `frontend/dist` at `/`, mounted after routes, auto-enabled when dist exists → Task 1 (`mount_frontend` + main.py wiring). ✓
- Single origin / relative `/api` unchanged → no `VITE_API_BASE` introduced. ✓
- `desktop.py` reuse-if-running, health-wait, clean shutdown, missing-dist message → Task 3 `main()`. ✓
- Double-click `.cmd` + optional Desktop shortcut script → Task 3. ✓
- pywebview in `backend/requirements.txt`, installed into venv, **lazy-imported** → Task 2 + Task 3 (`import webview` inside `main()`). ✓
- Testable logic in the `app` package; `desktop.py` thin with `--check` headless path → Tasks 1–3. ✓
- 158 tests stay green; new tests added → Task 1 (160) + Task 2 (163) regression steps. ✓
- Out of scope (installer, signing, worker bundling, FL/Flapi changes) — not touched. ✓

**Placeholder scan:** No TBD/TODO; every code step is complete; commands have expected output. The pywebview pin is a range (`>=5,<6`) with an explicit import-verify step and an escalation instruction if install fails — concrete, not a placeholder.

**Type consistency:** `mount_frontend(app, dist_dir) -> bool` (Task 1) is self-contained. `frontend_dist(app_root) -> Path` and `backend_is_up(base_url, timeout) -> bool` (Task 2) are consumed by `desktop.py` (Task 3) with identical signatures. `--check` returns `int` exit codes consistently. The health contract (`GET /api/health` → 200) used by `backend_is_up` matches the existing endpoint.
