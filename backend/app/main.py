from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .bridge import probe_bridge, run_transport_action
from .bridge_setup import build_bridge_setup_plan, install_bridge_server_scripts
from .contracts import ContractError
from .fl_scripts import install_piano_roll_script
from .generator import generate_payload, generate_song_draft
from .mastering import generate_mastering_plan
from .paths import detect_paths
from .store import PayloadStore

APP_ROOT = Path(__file__).resolve().parents[2]
STORE = PayloadStore(APP_ROOT / ".data")

app = FastAPI(title="FL Connector", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=3)
    genre: str = "Amapiano"
    bpm: int = Field(default=113, ge=40, le=240)
    key: str = "A"
    scale: str = "minor"
    bars: int = Field(default=4, ge=1, le=32)


class SongGenerateRequest(BaseModel):
    prompt: str = Field(min_length=3)
    genre: str = "Amapiano"
    bpm: int = Field(default=113, ge=40, le=240)
    key: str = "A"
    scale: str = "minor"
    bars: int = Field(default=8, ge=4, le=32)


class MasteringGenerateRequest(BaseModel):
    prompt: str = Field(min_length=3)
    genre: str = "Amapiano"
    bpm: int = Field(default=113, ge=40, le=240)


class BridgeInstallRequest(BaseModel):
    force: bool = False


class BridgeTransportRequest(BaseModel):
    action: str = Field(pattern="^(play|stop)$")


@app.on_event("startup")
def startup() -> None:
    STORE.ensure()
    STORE.event("server", "Connector backend started")


@app.get("/api/health")
def health() -> dict[str, Any]:
    paths = detect_paths()
    current = STORE.current()
    current_song = STORE.current_song()
    current_mastering = STORE.current_mastering_plan()
    return {
        "ok": True,
        "paths": paths.to_dict(),
        "currentPayload": current.to_dict() if current else None,
        "currentSong": current_song.to_dict() if current_song else None,
        "currentMasteringPlan": current_mastering.to_dict() if current_mastering else None,
        "events": STORE.events(12),
    }


@app.get("/api/bridge/health")
def bridge_health() -> dict[str, Any]:
    return probe_bridge().to_dict()


@app.post("/api/bridge/transport")
def bridge_transport(request: BridgeTransportRequest) -> dict[str, Any]:
    try:
        return run_transport_action(request.action).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/bridge/setup")
def bridge_setup() -> dict[str, Any]:
    return build_bridge_setup_plan(detect_paths()).to_dict()


@app.post("/api/bridge/setup/install-scripts")
def install_bridge_scripts(request: BridgeInstallRequest) -> dict[str, Any]:
    paths = detect_paths()
    try:
        result = install_bridge_server_scripts(paths, force=request.force)
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=400, detail="flapi is not installed in the backend") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Flapi server scripts already exist at {exc}",
        ) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    STORE.event("bridge-setup", f"Installed Flapi server scripts to {result['target']}")
    return result


@app.post("/api/install")
def install() -> dict[str, Any]:
    paths = detect_paths()
    try:
        installed = install_piano_roll_script(paths)
    except OSError as exc:
        STORE.event("error", f"Install failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    STORE.event("installed", f"Installed Piano Roll script to {installed}")
    return {"installedScriptPath": str(installed), "paths": paths.to_dict()}


@app.post("/api/generate")
def generate(request: GenerateRequest) -> dict[str, Any]:
    try:
        payload = generate_payload(
            prompt=request.prompt,
            genre=request.genre,
            bpm=request.bpm,
            key=request.key,
            scale=request.scale,
            bars=request.bars,
        )
        STORE.save_draft(payload)
    except ContractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return payload.to_dict()


@app.post("/api/songs/generate")
def generate_song(request: SongGenerateRequest) -> dict[str, Any]:
    try:
        draft = generate_song_draft(
            prompt=request.prompt,
            genre=request.genre,
            bpm=request.bpm,
            key=request.key,
            scale=request.scale,
            bars=request.bars,
        )
        STORE.save_song_draft(draft)
    except ContractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return draft.to_dict()


@app.get("/api/songs/current")
def current_song() -> dict[str, Any] | None:
    song = STORE.current_song()
    return song.to_dict() if song else None


@app.post("/api/mastering/generate")
def generate_mastering(request: MasteringGenerateRequest) -> dict[str, Any]:
    try:
        plan = generate_mastering_plan(
            prompt=request.prompt,
            genre=request.genre,
            bpm=request.bpm,
        )
        STORE.save_mastering_plan(plan)
    except ContractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return plan.to_dict()


@app.post("/api/mastering/{plan_id}/approve")
def approve_mastering(plan_id: str) -> dict[str, Any]:
    paths = detect_paths()
    try:
        plan = STORE.approve_mastering_plan(plan_id, paths.mastering_plan_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="mastering plan not found") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return plan.to_dict()


@app.get("/api/mastering/current")
def current_mastering_plan() -> dict[str, Any] | None:
    plan = STORE.current_mastering_plan()
    return plan.to_dict() if plan else None


@app.post("/api/payloads/{payload_id}/approve")
def approve(payload_id: str) -> dict[str, Any]:
    paths = detect_paths()
    try:
        payload = STORE.approve(payload_id, paths.payload_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="payload not found") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return payload.to_dict()


@app.get("/api/payloads/current")
def current_payload() -> dict[str, Any] | None:
    current = STORE.current()
    return current.to_dict() if current else None


@app.get("/api/events")
def events() -> list[dict[str, object]]:
    return STORE.events(50)
