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
