from __future__ import annotations

import shutil
from pathlib import Path

from .paths import FlPaths


def source_script_path() -> Path:
    return Path(__file__).resolve().parents[1] / "fl_scripts" / "FL Connector Apply Payload.pyscript"


def install_piano_roll_script(paths: FlPaths) -> Path:
    paths.piano_roll_scripts.mkdir(parents=True, exist_ok=True)
    paths.connector_data.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_script_path(), paths.installed_script_path)
    return paths.installed_script_path
