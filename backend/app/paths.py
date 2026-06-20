from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FlPaths:
    image_line_data_dir: Path
    documents_root: Path
    settings_root: Path
    hardware_scripts: Path
    flapi_server_scripts: Path
    piano_roll_scripts: Path
    connector_data: Path
    payload_path: Path
    mastering_plan_path: Path
    installed_script_path: Path
    fl_studio_2025: Path

    def to_dict(self) -> dict[str, object]:
        return {
            "imageLineDataDir": str(self.image_line_data_dir),
            "documentsRoot": str(self.documents_root),
            "settingsRoot": str(self.settings_root),
            "hardwareScripts": str(self.hardware_scripts),
            "flapiServerScripts": str(self.flapi_server_scripts),
            "pianoRollScripts": str(self.piano_roll_scripts),
            "connectorData": str(self.connector_data),
            "payloadPath": str(self.payload_path),
            "masteringPlanPath": str(self.mastering_plan_path),
            "installedScriptPath": str(self.installed_script_path),
            "flStudio2025": str(self.fl_studio_2025),
            "exists": {
                "documentsRoot": self.documents_root.exists(),
                "settingsRoot": self.settings_root.exists(),
                "hardwareScripts": self.hardware_scripts.exists(),
                "flapiServerScripts": self.flapi_server_scripts.exists(),
                "pianoRollScripts": self.piano_roll_scripts.exists(),
                "connectorData": self.connector_data.exists(),
                "payloadPath": self.payload_path.exists(),
                "masteringPlanPath": self.mastering_plan_path.exists(),
                "installedScriptPath": self.installed_script_path.exists(),
                "flStudio2025": self.fl_studio_2025.exists(),
            },
        }


def detect_paths(home: Path | None = None) -> FlPaths:
    user_home = home or Path.home()
    image_line_data_dir = user_home / "Documents" / "Image-Line"
    documents_root = image_line_data_dir / "FL Studio"
    settings_root = documents_root / "Settings"
    hardware_scripts = settings_root / "Hardware"
    piano_roll_scripts = settings_root / "Piano roll scripts"
    connector_data = piano_roll_scripts / "FL Connector"
    return FlPaths(
        image_line_data_dir=image_line_data_dir,
        documents_root=documents_root,
        settings_root=settings_root,
        hardware_scripts=hardware_scripts,
        flapi_server_scripts=hardware_scripts / "Flapi Server",
        piano_roll_scripts=piano_roll_scripts,
        connector_data=connector_data,
        payload_path=connector_data / "pending_payload.json",
        mastering_plan_path=connector_data / "approved_mastering_plan.json",
        installed_script_path=piano_roll_scripts / "FL Connector Apply Payload.pyscript",
        fl_studio_2025=Path("C:/Program Files/Image-Line/FL Studio 2025"),
    )
