from pathlib import Path

from app.mastering import generate_mastering_plan
from app.paths import detect_paths


def test_mastering_plan_uses_builtin_fl_effects():
    plan = generate_mastering_plan(
        prompt="Master this deep amapiano draft professionally",
        genre="Amapiano",
        bpm=113,
    )

    plugins = {step.plugin for step in plan.steps}
    assert "Fruity Parametric EQ 2" in plugins
    assert "Fruity Limiter" in plugins
    assert "Maximus" in plugins
    assert any(step.target == "master" for step in plan.steps)
    assert len(plan.steps) == 12
    assert plan.status == "draft"


def test_mastering_path_is_in_connector_data_folder():
    paths = detect_paths(Path("C:/Users/Example"))

    assert paths.mastering_plan_path.name == "approved_mastering_plan.json"
    assert paths.mastering_plan_path.parent.name == "FL Connector"
