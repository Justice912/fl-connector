from pathlib import Path

import pytest

from app.bridge_setup import build_bridge_setup_plan, install_bridge_server_scripts
from app.contracts import BridgeSetupPlan, ContractError
from app.main import bridge_setup
from app.paths import detect_paths


def test_bridge_setup_plan_reports_missing_requirements(tmp_path: Path):
    paths = detect_paths(tmp_path)
    paths.hardware_scripts.mkdir(parents=True)

    plan = build_bridge_setup_plan(
        paths,
        module_checker=lambda name: False,
        midi_port_provider=lambda: ([], []),
    )

    assert plan.status == "needs_action"
    assert plan.canInstallScripts is False
    assert plan.to_dict()["checks"][0]["status"] == "ready"
    assert any(check.key == "python_flapi" and check.status == "missing" for check in plan.checks)
    assert any(check.key == "midi_request_port" and check.status == "missing" for check in plan.checks)
    assert any("Options > MIDI Settings" in step for step in plan.manualSteps)


def test_bridge_setup_plan_reports_ready_when_all_checks_pass(tmp_path: Path):
    paths = detect_paths(tmp_path)
    paths.hardware_scripts.mkdir(parents=True)
    paths.flapi_server_scripts.mkdir()

    plan = build_bridge_setup_plan(
        paths,
        module_checker=lambda name: name in {"flapi", "mido"},
        midi_port_provider=lambda: (["Flapi Response 1"], ["Flapi Request 1"]),
    )

    assert plan.status == "ready"
    assert plan.canInstallScripts is False
    assert all(check.status == "ready" for check in plan.checks if check.blocking)


def test_bridge_setup_plan_round_trips():
    plan = BridgeSetupPlan.from_dict(
        {
            "status": "needs_action",
            "message": "Bridge needs setup.",
            "canInstallScripts": True,
            "installCommand": "POST /api/bridge/setup/install-scripts",
            "manualSteps": ["Restart FL Studio."],
            "checks": [
                {
                    "key": "python_flapi",
                    "label": "Flapi Python package",
                    "status": "ready",
                    "detail": "Import works.",
                    "action": "",
                    "blocking": True,
                }
            ],
        }
    )

    assert plan.to_dict()["checks"][0]["key"] == "python_flapi"


def test_bridge_setup_plan_rejects_empty_checks():
    with pytest.raises(ContractError):
        BridgeSetupPlan.from_dict(
            {
                "status": "ready",
                "message": "Bad plan.",
                "canInstallScripts": False,
                "installCommand": None,
                "manualSteps": [],
                "checks": [],
            }
        )


def test_install_bridge_server_scripts_copies_source_without_overwrite(tmp_path: Path):
    paths = detect_paths(tmp_path)
    source = tmp_path / "source-server"
    source.mkdir()
    (source / "device_test.py").write_text("# test", encoding="utf-8")

    result = install_bridge_server_scripts(paths, source_dir=source)

    assert result["installed"] is True
    assert (paths.flapi_server_scripts / "device_test.py").exists()

    with pytest.raises(FileExistsError):
        install_bridge_server_scripts(paths, source_dir=source)


def test_install_bridge_server_scripts_can_force_replace(tmp_path: Path):
    paths = detect_paths(tmp_path)
    source = tmp_path / "source-server"
    source.mkdir()
    (source / "device_test.py").write_text("# next", encoding="utf-8")
    paths.flapi_server_scripts.mkdir(parents=True)
    (paths.flapi_server_scripts / "old.py").write_text("# old", encoding="utf-8")

    result = install_bridge_server_scripts(paths, source_dir=source, force=True)

    assert result["installed"] is True
    assert not (paths.flapi_server_scripts / "old.py").exists()
    assert (paths.flapi_server_scripts / "device_test.py").read_text(encoding="utf-8") == "# next"


def test_bridge_setup_endpoint_returns_plan():
    body = bridge_setup()

    assert body["status"] in {"ready", "needs_action", "error"}
    assert any(check["key"] == "python_flapi" for check in body["checks"])
