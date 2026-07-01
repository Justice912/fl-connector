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
