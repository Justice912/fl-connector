from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from .analysis import LocalAnalysisProvider
from .analysis_jobs import AnalysisJobRunner
from .analysis_setup import build_analysis_setup_plan, install_analysis_worker, worker_python
from .bridge import probe_bridge, run_transport_action
from .bridge_setup import build_bridge_setup_plan, install_bridge_server_scripts
from .contracts import ContractError, NotePayload
from .fl_scripts import install_piano_roll_script
from .generator import generate_payload, generate_song_draft
from .mastering import generate_mastering_plan
from .inventory import InventoryScanner, InventorySnapshot
from .paths import detect_paths
from .reconstruction_compiler import ReconstructionCompiler
from .reconstruction_contracts import ReconstructionError, ReconstructionProject, ReconstructedPart
from .reconstruction_export import build_reconstruction_export
from .reconstruction_store import MAX_PROJECT_BYTES, ReconstructionStore, UploadCandidate
from .store import PayloadStore

APP_ROOT = Path(__file__).resolve().parents[2]
STORE = PayloadStore(APP_ROOT / ".data")
RECONSTRUCTION_STORE = ReconstructionStore(APP_ROOT / ".data" / "reconstructions")
CATALOG_PATH = APP_ROOT / "backend" / "app" / "recommendation_catalog.json"
INVENTORY_ROOTS_PATH = APP_ROOT / ".data" / "inventory_roots.json"

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


class AnalysisInstallRequest(BaseModel):
    approved: bool = False


class ReconstructionCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    rightsAccepted: bool = False
    genreProfile: str = "south_african_dance"


class ReconstructionPatchRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    bpm: float | None = Field(default=None, ge=40, le=240)
    key: str | None = None
    scale: str | None = Field(default=None, pattern="^(major|minor)$")


class ReconstructionPartPatchRequest(BaseModel):
    role: str | None = None
    outputMode: str | None = Field(default=None, pattern="^(midi|audio)$")
    selectedSoundId: str | None = None


class GuideStepPatchRequest(BaseModel):
    completed: bool


class InventoryRefreshRequest(BaseModel):
    extraRoots: list[str] = Field(default_factory=list)


@app.on_event("startup")
def startup() -> None:
    STORE.ensure()
    RECONSTRUCTION_STORE.ensure()
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


@app.get("/api/analysis/setup")
def analysis_setup() -> dict[str, object]:
    return build_analysis_setup_plan(APP_ROOT)


@app.post("/api/analysis/setup/install")
def analysis_install(request: AnalysisInstallRequest) -> dict[str, object]:
    try:
        return install_analysis_worker(APP_ROOT, approved=request.approved)
    except ReconstructionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/reconstructions", status_code=201)
def create_reconstruction(request: ReconstructionCreateRequest) -> dict[str, Any]:
    try:
        project = RECONSTRUCTION_STORE.create_project(
            request.title,
            rights_accepted=request.rightsAccepted,
            genre_profile=request.genreProfile,
        )
    except ReconstructionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return project.to_dict()


@app.get("/api/reconstructions")
def list_reconstructions() -> list[dict[str, Any]]:
    return [project.to_dict() for project in RECONSTRUCTION_STORE.list_projects()]


@app.get("/api/reconstructions/{project_id}")
def get_reconstruction(project_id: str) -> dict[str, Any]:
    try:
        return RECONSTRUCTION_STORE.get(project_id).to_dict()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reconstruction project not found") from exc


@app.post("/api/reconstructions/{project_id}/stems")
async def upload_reconstruction_stems(
    project_id: str,
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    uploads = []
    total = 0
    for file in files:
        data = await file.read()
        total += len(data)
        if total > MAX_PROJECT_BYTES:
            raise HTTPException(status_code=413, detail="upload exceeds the 1 GB project limit")
        uploads.append(UploadCandidate(fileName=file.filename or "upload", data=data))
    try:
        return RECONSTRUCTION_STORE.add_uploads(project_id, uploads).to_dict()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reconstruction project not found") from exc
    except ReconstructionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/reconstructions/{project_id}/stems/{stem_id}/content")
def reconstruction_stem_content(project_id: str, stem_id: str) -> FileResponse:
    try:
        path, stem = RECONSTRUCTION_STORE.stem_path(project_id, stem_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reconstruction stem not found") from exc
    return FileResponse(path, media_type=stem.mediaType, filename=stem.fileName)


@app.patch("/api/reconstructions/{project_id}")
def patch_reconstruction(
    project_id: str,
    request: ReconstructionPatchRequest,
) -> dict[str, Any]:
    try:
        project = RECONSTRUCTION_STORE.get(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reconstruction project not found") from exc
    changes = request.model_dump(exclude_none=True)
    title = changes.pop("title", None)
    overrides = {key: value for key, value in changes.items() if key in {"bpm", "key", "scale"}}
    if title is not None:
        project = project.with_changes(title=title.strip())
    if overrides:
        project = project.with_changes(
            status="uploaded",
            analysisOverrides={**project.analysisOverrides, **overrides},
            analysisJob=None,
            analysisSummary=None,
            parts=[],
            timeline=[],
            soundMatches=[],
            guideSteps=[],
            mixPlan=None,
            warnings=["Analysis settings changed; run analysis again."],
        )
    return RECONSTRUCTION_STORE.save(project).to_dict()


@app.delete("/api/reconstructions/{project_id}", status_code=204)
def delete_reconstruction(project_id: str) -> Response:
    try:
        RECONSTRUCTION_STORE.delete(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reconstruction project not found") from exc
    return Response(status_code=204)


@app.post("/api/reconstructions/{project_id}/cleanup")
def cleanup_reconstruction(project_id: str) -> dict[str, Any]:
    try:
        return RECONSTRUCTION_STORE.clear_derived(project_id).to_dict()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reconstruction project not found") from exc


@app.post("/api/reconstructions/{project_id}/analyze", status_code=202)
def analyze_reconstruction(project_id: str) -> dict[str, Any]:
    setup = build_analysis_setup_plan(APP_ROOT)
    if not setup["ready"]:
        raise HTTPException(status_code=409, detail="local analysis worker is not ready")
    try:
        runner = _analysis_runner()
        return runner.start(project_id).to_dict()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reconstruction project not found") from exc
    except ReconstructionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/reconstructions/{project_id}/retry", status_code=202)
def retry_reconstruction(project_id: str) -> dict[str, Any]:
    return analyze_reconstruction(project_id)


@app.patch("/api/reconstructions/{project_id}/parts/{part_id}")
def patch_reconstruction_part(
    project_id: str,
    part_id: str,
    request: ReconstructionPartPatchRequest,
) -> dict[str, Any]:
    try:
        project = RECONSTRUCTION_STORE.get(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reconstruction project not found") from exc
    values = request.model_dump(exclude_none=True)
    if values.get("selectedSoundId") and values["selectedSoundId"] not in {
        item.id for item in project.soundMatches
    }:
        raise HTTPException(status_code=400, detail="selected sound is not in project recommendations")
    changed = False
    parts = []
    try:
        for part in project.parts:
            if part.id != part_id:
                parts.append(part)
                continue
            parts.append(ReconstructedPart.from_dict({**part.to_dict(), **values}))
            changed = True
    except ReconstructionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not changed:
        raise HTTPException(status_code=404, detail="reconstruction part not found")
    return RECONSTRUCTION_STORE.save(project.with_changes(parts=parts)).to_dict()


@app.post(
    "/api/reconstructions/{project_id}/parts/{part_id}/patterns/{pattern_id}/approve"
)
def approve_reconstruction_pattern(
    project_id: str,
    part_id: str,
    pattern_id: str,
) -> dict[str, Any]:
    try:
        project = RECONSTRUCTION_STORE.get(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reconstruction project not found") from exc
    data = project.to_dict()
    selected = None
    for part in data["parts"]:
        if part["id"] != part_id:
            continue
        for pattern in part["patterns"]:
            if pattern["id"] != pattern_id:
                continue
            selected = pattern
            break
    if selected is None:
        raise HTTPException(status_code=404, detail="reconstruction pattern not found")
    payload = NotePayload.from_dict(selected["payload"])
    STORE.save_draft(payload)
    approved = STORE.approve(payload.id, detect_paths().payload_path)
    selected["payload"] = approved.to_dict()
    for part in data["parts"]:
        if part["id"] == part_id:
            part["approved"] = all(
                pattern["payload"]["status"] == "approved" for pattern in part["patterns"]
            )
    updated = RECONSTRUCTION_STORE.save(ReconstructionProject.from_dict(data))
    return {"project": updated.to_dict(), "payload": approved.to_dict()}


@app.post("/api/reconstructions/{project_id}/parts/{part_id}/approve-audio")
def approve_reconstruction_audio(project_id: str, part_id: str) -> dict[str, Any]:
    try:
        project = RECONSTRUCTION_STORE.get(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reconstruction project not found") from exc
    data = project.to_dict()
    selected = next((part for part in data["parts"] if part["id"] == part_id), None)
    if selected is None or selected["outputMode"] != "audio":
        raise HTTPException(status_code=404, detail="audio reconstruction part not found")
    selected["approved"] = True
    return RECONSTRUCTION_STORE.save(ReconstructionProject.from_dict(data)).to_dict()


@app.get("/api/reconstructions/{project_id}/guide")
def reconstruction_guide(project_id: str) -> list[dict[str, Any]]:
    return get_reconstruction(project_id)["guideSteps"]


@app.patch("/api/reconstructions/{project_id}/guide/{step_id}")
def patch_guide_step(
    project_id: str,
    step_id: str,
    request: GuideStepPatchRequest,
) -> dict[str, Any]:
    try:
        project = RECONSTRUCTION_STORE.get(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reconstruction project not found") from exc
    data = project.to_dict()
    selected = next((step for step in data["guideSteps"] if step["id"] == step_id), None)
    if selected is None:
        raise HTTPException(status_code=404, detail="guide step not found")
    selected["completed"] = request.completed
    return RECONSTRUCTION_STORE.save(ReconstructionProject.from_dict(data)).to_dict()


@app.get("/api/inventory")
def inventory() -> dict[str, object]:
    return _scan_inventory().to_dict()


@app.post("/api/inventory/refresh")
def refresh_inventory(request: InventoryRefreshRequest) -> dict[str, object]:
    INVENTORY_ROOTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    INVENTORY_ROOTS_PATH.write_text(json.dumps(request.extraRoots, indent=2), encoding="utf-8")
    return _scan_inventory().to_dict()


@app.get("/api/reconstructions/{project_id}/export")
def export_reconstruction(project_id: str) -> StreamingResponse:
    try:
        project = RECONSTRUCTION_STORE.get(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reconstruction project not found") from exc
    bundle = build_reconstruction_export(project, RECONSTRUCTION_STORE.project_dir(project_id))
    filename = "".join(char if char.isalnum() or char in "-_" else "_" for char in project.title)
    return StreamingResponse(
        BytesIO(bundle),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename or "reconstruction"}.zip"'},
    )


def _analysis_runner() -> AnalysisJobRunner:
    catalog = InventoryScanner.load_catalog(CATALOG_PATH)
    return AnalysisJobRunner(
        RECONSTRUCTION_STORE,
        LocalAnalysisProvider(worker_python(APP_ROOT), APP_ROOT / "backend"),
        ReconstructionCompiler(catalog),
        inventory_provider=_scan_inventory,
    )


def _scan_inventory() -> InventorySnapshot:
    paths = detect_paths()
    roots = [
        paths.documents_root / "Presets" / "Plugin database",
        paths.fl_studio_2025 / "Data" / "Patches" / "Plugin database",
        paths.fl_studio_2025 / "Data" / "Patches" / "Packs",
        Path("C:/Program Files/Common Files/VST3"),
    ]
    if INVENTORY_ROOTS_PATH.exists():
        try:
            roots.extend(Path(item) for item in json.loads(INVENTORY_ROOTS_PATH.read_text()))
        except (OSError, ValueError, TypeError):
            pass
    return InventoryScanner(roots).scan()
