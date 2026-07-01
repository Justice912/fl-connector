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
