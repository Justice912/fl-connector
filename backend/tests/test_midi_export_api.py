from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app.paths import detect_paths
from app.store import PayloadStore


def isolated_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr(main, "STORE", PayloadStore(tmp_path / "payloads"))
    monkeypatch.setattr(main, "detect_paths", lambda: detect_paths(tmp_path))
    return TestClient(main.app)


def test_export_song_midi_returns_midi_file(tmp_path: Path, monkeypatch):
    client = isolated_client(tmp_path, monkeypatch)
    draft = client.post(
        "/api/songs/generate",
        json={"prompt": "deep amapiano song draft", "bars": 8},
    ).json()

    response = client.get(f"/api/songs/{draft['id']}/export-midi")

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/midi"
    assert ".mid" in response.headers["content-disposition"]
    assert response.content[:4] == b"MThd"


def test_export_payload_midi_returns_midi_file(tmp_path: Path, monkeypatch):
    client = isolated_client(tmp_path, monkeypatch)
    payload = client.post(
        "/api/generate",
        json={"prompt": "amapiano log drum riff"},
    ).json()

    response = client.get(f"/api/payloads/{payload['id']}/export-midi")

    assert response.status_code == 200
    assert response.content[:4] == b"MThd"
    assert response.headers["content-type"] == "audio/midi"
    assert ".mid" in response.headers["content-disposition"]


def test_export_song_midi_unknown_id_returns_404(tmp_path: Path, monkeypatch):
    client = isolated_client(tmp_path, monkeypatch)
    response = client.get("/api/songs/does-not-exist/export-midi")
    assert response.status_code == 404


def test_export_payload_midi_unknown_id_returns_404(tmp_path: Path, monkeypatch):
    client = isolated_client(tmp_path, monkeypatch)
    response = client.get("/api/payloads/does-not-exist/export-midi")
    assert response.status_code == 404
