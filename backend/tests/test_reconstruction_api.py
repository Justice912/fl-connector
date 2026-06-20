from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app import main
from app.contracts import Note, NotePayload
from app.paths import detect_paths
from app.reconstruction_contracts import (
    AnalysisSummary,
    GuideStep,
    PatternSlice,
    ReconstructedPart,
)
from app.reconstruction_store import ReconstructionStore, UploadCandidate
from app.store import PayloadStore


def wav_bytes() -> bytes:
    return b"RIFF" + (40).to_bytes(4, "little") + b"WAVEfmt " + b"\x00" * 32


def isolated_client(tmp_path: Path, monkeypatch) -> TestClient:
    reconstruction_store = ReconstructionStore(tmp_path / "reconstructions")
    payload_store = PayloadStore(tmp_path / "payloads")
    monkeypatch.setattr(main, "RECONSTRUCTION_STORE", reconstruction_store)
    monkeypatch.setattr(main, "STORE", payload_store)
    monkeypatch.setattr(main, "detect_paths", lambda: detect_paths(tmp_path))
    return TestClient(main.app)


def test_create_requires_rights_and_uploads_valid_stem(tmp_path: Path, monkeypatch):
    client = isolated_client(tmp_path, monkeypatch)

    denied = client.post(
        "/api/reconstructions",
        json={"title": "No permission", "rightsAccepted": False},
    )
    created = client.post(
        "/api/reconstructions",
        json={"title": "Owned Suno song", "rightsAccepted": True},
    )
    project_id = created.json()["id"]
    uploaded = client.post(
        f"/api/reconstructions/{project_id}/stems",
        files=[("files", ("bass.wav", wav_bytes(), "audio/wav"))],
    )

    assert denied.status_code == 400
    assert created.status_code == 201
    assert uploaded.status_code == 200
    assert uploaded.json()["stems"][0]["role"] == "bass"
    assert client.get("/api/reconstructions").json()[0]["id"] == project_id


def test_uploaded_stem_can_be_previewed_locally(tmp_path: Path, monkeypatch):
    client = isolated_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/reconstructions",
        json={"title": "Owned preview", "rightsAccepted": True},
    ).json()
    uploaded = client.post(
        f"/api/reconstructions/{created['id']}/stems",
        files=[("files", ("bass.wav", wav_bytes(), "audio/wav"))],
    ).json()

    response = client.get(
        f"/api/reconstructions/{created['id']}/stems/{uploaded['stems'][0]['id']}/content"
    )

    assert response.status_code == 200
    assert response.content == wav_bytes()
    assert response.headers["content-type"] == "audio/wav"


def test_metadata_correction_invalidates_derived_blueprint(tmp_path: Path, monkeypatch):
    client = isolated_client(tmp_path, monkeypatch)
    store = main.RECONSTRUCTION_STORE
    project = store.create_project("Owned", rights_accepted=True)
    project = store.add_uploads(
        project.id,
        [UploadCandidate(fileName="bass.wav", data=wav_bytes())],
    )
    summary = AnalysisSummary.from_dict(
        {
            "bpm": 114,
            "bpmConfidence": 0.9,
            "key": "G",
            "scale": "minor",
            "keyConfidence": 0.8,
            "timeSignature": "4/4",
            "durationSeconds": 8,
            "sections": [],
        }
    )
    store.save(project.with_changes(status="review", analysisSummary=summary, mixPlan={"steps": []}))

    response = client.patch(
        f"/api/reconstructions/{project.id}",
        json={"bpm": 115, "key": "A", "scale": "minor"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "uploaded"
    assert response.json()["analysisOverrides"] == {"bpm": 115.0, "key": "A", "scale": "minor"}
    assert response.json()["analysisSummary"] is None
    assert response.json()["parts"] == []


def test_approve_pattern_writes_existing_fl_payload_and_exports_bundle(tmp_path: Path, monkeypatch):
    client = isolated_client(tmp_path, monkeypatch)
    store = main.RECONSTRUCTION_STORE
    project = store.create_project("Owned", rights_accepted=True)
    project = store.add_uploads(
        project.id,
        [UploadCandidate(fileName="bass.wav", data=wav_bytes())],
    )
    payload = NotePayload.create(
        title="Bass A",
        sourcePrompt="Owned reconstruction",
        genre="South African dance",
        bpm=114,
        key="G",
        scale="minor",
        bars=4,
        notes=[Note(pitch=43, startBeats=0, durationBeats=1)],
    )
    pattern = PatternSlice.create(name="Bass A", startBar=1, payload=payload)
    part = ReconstructedPart.create(
        sourceStemId=project.stems[0].id,
        name="Bass",
        role="bass",
        outputMode="midi",
        confidence=0.9,
        patterns=[pattern],
    )
    guide = GuideStep.from_dict(
        {
            "order": 1,
            "title": "Open Piano Roll",
            "area": "Piano Roll",
            "action": "Open it",
            "menuPath": "Channel Rack > Piano Roll",
            "shortcut": "F7",
            "imageAsset": "/guides/fl-2025/apply-payload.png",
            "hotspot": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
            "expectedState": "Piano Roll visible",
        }
    )
    store.save(project.with_changes(status="review", parts=[part], guideSteps=[guide]))

    approved = client.post(
        f"/api/reconstructions/{project.id}/parts/{part.id}/patterns/{pattern.id}/approve"
    )
    guide_done = client.patch(
        f"/api/reconstructions/{project.id}/guide/{guide.id}",
        json={"completed": True},
    )
    exported = client.get(f"/api/reconstructions/{project.id}/export")

    assert approved.status_code == 200
    assert approved.json()["payload"]["status"] == "approved"
    assert detect_paths(tmp_path).payload_path.exists()
    assert guide_done.json()["guideSteps"][0]["completed"] is True
    assert exported.status_code == 200
    with ZipFile(BytesIO(exported.content)) as bundle:
        assert "midi/Bass/Bass A.mid" in bundle.namelist()


def test_delete_project_removes_it_from_listing(tmp_path: Path, monkeypatch):
    client = isolated_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/reconstructions",
        json={"title": "Owned", "rightsAccepted": True},
    ).json()

    response = client.delete(f"/api/reconstructions/{created['id']}")

    assert response.status_code == 204
    assert client.get("/api/reconstructions").json() == []
