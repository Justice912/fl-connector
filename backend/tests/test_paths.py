from pathlib import Path

from app.paths import detect_paths


def test_detect_paths_uses_image_line_settings():
    paths = detect_paths(Path("C:/Users/Example"))

    assert "Image-Line" in str(paths.piano_roll_scripts)
    assert paths.installed_script_path.name == "FL Connector Apply Payload.pyscript"
    assert paths.payload_path.name == "pending_payload.json"
