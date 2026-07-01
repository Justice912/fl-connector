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
