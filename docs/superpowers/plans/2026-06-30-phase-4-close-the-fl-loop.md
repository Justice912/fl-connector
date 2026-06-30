# Phase 4 — Close the FL Loop for Rebuild — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Rebuild (audio reconstruction) feature a one-drag multi-track MIDI export plus a server-side Flapi "sync" that sets tempo and channel/mixer-track names to match the reconstruction.

**Architecture:** A pure MIDI builder (`reconstruction_to_midi`) reuses the existing Phase 1 encoder in `midi_export.py`; a new pure planner (`build_sync_plan`) in `reconstruction_sync.py` computes a sync plan from a live bridge snapshot and an orchestrator applies it through the existing, verified bridge write functions. Two FastAPI endpoints expose them; the React workspace gains a "Send to FL" card.

**Tech Stack:** Python 3 / FastAPI (backend, pytest), React + Vite (frontend, vitest). Flapi bridge (FL Studio MIDI Controller scripting) already wired in `bridge.py`.

## Global Constraints

- The multi-track MIDI spine uses **PPQ 96, Format-1**, identical to the generator (`song_to_midi`). Reuse the private helpers in `midi_export.py` (`_conductor_track`, `_encode_track`, `_note_events`, `_header`) — do not re-implement MIDI byte encoding.
- **No new third-party dependencies.**
- The sync sets **tempo + channel names + mixer-track names only**. The mix plan has no numeric volume/pan values — **do not fabricate** levels.
- Bridge writes go through the **existing** functions in `bridge.py` (`probe_bridge`, `run_bridge_write`); the orchestrator must accept an injectable `client_factory` for tests (same pattern as `bridge.py`).
- Channel naming uses **global indexing** (`useGlobalIndex=True`), matching Phase 2b. Mapping: MIDI part `i` (0-based, in `project.parts` order) → channel index `i`; → mixer insert index `i + 1` (insert 0 is the FL master).
- FL tempo range is **40–240 BPM** (already enforced by `set_project_tempo`; the analysis summary BPM is always in range).
- The reconstruction ZIP **keeps** its existing per-pattern `midi/<part>/<pattern>.mid` files; the spine is added as a new `arrangement.mid`.
- Guide-step `imageAsset` paths must stay under `/guides/fl-2025/` (reuse existing SVG filenames; no new image assets).
- All builders/planners are deterministic and pure (no I/O).

---

### Task 1: Multi-track MIDI builder (`reconstruction_to_midi`)

**Files:**
- Modify: `backend/app/midi_export.py` (add one public function + one import)
- Test: `backend/tests/test_midi_export.py` (add tests; reuse existing `parse_midi` helper)

**Interfaces:**
- Consumes: `midi_export._conductor_track`, `_encode_track`, `_note_events`, `_header` (existing private helpers); `contracts.Note`; `reconstruction_contracts.ReconstructionProject`, `ReconstructedPart`, `PatternSlice`.
- Produces: `reconstruction_to_midi(project: ReconstructionProject) -> bytes` — a Format-1 multi-track MIDI: conductor track (tempo from `project.analysisSummary.bpm`, 4/4) followed by one track per MIDI part (`outputMode == "midi"`), named `part.name`, channel `partIndex % 16`, with every pattern's notes placed at absolute positions (`startBeats + (placementBar - 1) * 4` for each bar in `pattern.placements`). Audio parts excluded.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_midi_export.py` (the `parse_midi` helper already exists in this file):

```python
def _reconstruction_with_midi_part():
    from app.contracts import Note, NotePayload
    from app.reconstruction_contracts import (
        AnalysisSummary,
        PatternSlice,
        ReconstructedPart,
        ReconstructionProject,
    )

    project = ReconstructionProject.create(title="Owned rebuild", rightsAccepted=True)
    payload = NotePayload.create(
        title="Bass bars 1-2",
        sourcePrompt="Reconstructed",
        genre="South African dance",
        bpm=112,
        key="G",
        scale="minor",
        bars=2,
        notes=[Note(40, 0.0, 1.0, 0.8), Note(43, 4.0, 1.0, 0.8)],
    )
    pattern = PatternSlice.create(name="Bass bars 1-2", startBar=3, payload=payload)
    bass = ReconstructedPart.create(
        sourceStemId="stem-1",
        name="Bass",
        role="bass",
        outputMode="midi",
        confidence=0.9,
        patterns=[pattern],
    )
    vocals = ReconstructedPart.create(
        sourceStemId="stem-2",
        name="Vocals",
        role="vocals",
        outputMode="audio",
        confidence=0.95,
        audioRelativePath="audio/vocals.wav",
    )
    summary = AnalysisSummary.from_dict(
        {"bpm": 112, "bpmConfidence": 0.8, "key": "G", "scale": "minor",
         "keyConfidence": 0.8, "timeSignature": "4/4", "durationSeconds": 8.0,
         "integratedLoudness": None, "peakDb": None, "stereoWidth": None, "sections": []}
    )
    return project.with_changes(analysisSummary=summary, parts=[bass, vocals])


def test_reconstruction_to_midi_one_track_per_midi_part_with_absolute_notes():
    from app.midi_export import reconstruction_to_midi

    project = _reconstruction_with_midi_part()
    parsed = parse_midi(reconstruction_to_midi(project))

    # conductor + 1 MIDI part (the audio part is excluded)
    assert parsed["format"] == 1
    assert parsed["division"] == 96
    assert parsed["ntrks"] == 2
    assert parsed["tracks"][0]["tempo"] == round(60_000_000 / 112)
    assert parsed["tracks"][1]["name"] == "Bass"

    # pattern startBar=3 -> +8 beats; notes at 0.0 and 4.0 -> beats 8 and 12 -> ticks 768, 1152
    ticks = sorted(note[0] for note in parsed["tracks"][1]["notes"])
    assert ticks == [round(8 * 96), round(12 * 96)]


def test_reconstruction_to_midi_excludes_audio_parts():
    from app.midi_export import reconstruction_to_midi

    project = _reconstruction_with_midi_part()
    parsed = parse_midi(reconstruction_to_midi(project))
    assert [track["name"] for track in parsed["tracks"][1:]] == ["Bass"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_midi_export.py -k reconstruction -v`
Expected: FAIL with `ImportError: cannot import name 'reconstruction_to_midi'`.

- [ ] **Step 3: Implement the builder**

In `backend/app/midi_export.py`, add to the imports at the top (after the existing `from .contracts import ...` line):

```python
from dataclasses import replace

from .reconstruction_contracts import ReconstructionProject
```

(`reconstruction_contracts` imports only from `contracts`, so this adds no import cycle.)

Append at the end of `backend/app/midi_export.py`:

```python
def reconstruction_to_midi(project: ReconstructionProject) -> bytes:
    bpm = round(project.analysisSummary.bpm) if project.analysisSummary else 120
    tracks = [_conductor_track(project.title, bpm)]
    midi_parts = [part for part in project.parts if part.outputMode == "midi"]
    for index, part in enumerate(midi_parts):
        notes: list[Note] = []
        for pattern in part.patterns:
            for bar in pattern.placements:
                offset = (bar - 1) * 4
                for note in pattern.payload.notes:
                    notes.append(replace(note, startBeats=note.startBeats + offset))
        events = _note_events(notes, index % 16)
        tracks.append(_encode_track(events, part.name))
    return _header(len(tracks)) + b"".join(tracks)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_midi_export.py -v`
Expected: PASS (existing tests plus the two new ones).

- [ ] **Step 5: Commit**

```bash
git add backend/app/midi_export.py backend/tests/test_midi_export.py
git commit -m "feat: build one-drag multi-track MIDI for reconstructions"
```

---

### Task 2: `GET /api/reconstructions/{id}/export-midi` endpoint

**Files:**
- Modify: `backend/app/main.py` (extend the `midi_export` import; add one endpoint)
- Test: `backend/tests/test_reconstruction_api.py` (add tests; reuse `isolated_client`)

**Interfaces:**
- Consumes: `midi_export.reconstruction_to_midi` (Task 1); `main.RECONSTRUCTION_STORE`, `main._safe_filename` (existing).
- Produces: `GET /api/reconstructions/{project_id}/export-midi` → `audio/midi` attachment. `404` unknown project; `400` when the project has zero MIDI parts.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_reconstruction_api.py`. This builds a project through the store with one MIDI part (helper kept local to the test):

```python
def _seed_midi_project(reconstruction_store):
    from app.contracts import Note, NotePayload
    from app.reconstruction_contracts import PatternSlice, ReconstructedPart

    project = reconstruction_store.create(title="Owned rebuild", rightsAccepted=True)
    payload = NotePayload.create(
        title="Bass bars 1-1", sourcePrompt="Reconstructed", genre="South African dance",
        bpm=112, key="G", scale="minor", bars=1, notes=[Note(40, 0.0, 1.0, 0.8)],
    )
    pattern = PatternSlice.create(name="Bass bars 1-1", startBar=1, payload=payload)
    part = ReconstructedPart.create(
        sourceStemId="stem-1", name="Bass", role="bass", outputMode="midi",
        confidence=0.9, patterns=[pattern],
    )
    return reconstruction_store.save(project.with_changes(parts=[part]))


def test_export_midi_returns_multitrack_file(tmp_path, monkeypatch):
    client = isolated_client(tmp_path, monkeypatch)
    project = _seed_midi_project(main.RECONSTRUCTION_STORE)

    response = client.get(f"/api/reconstructions/{project.id}/export-midi")

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/midi"
    assert response.content[:4] == b"MThd"


def test_export_midi_404_for_unknown_and_400_when_no_midi_parts(tmp_path, monkeypatch):
    client = isolated_client(tmp_path, monkeypatch)
    missing = client.get("/api/reconstructions/does-not-exist/export-midi")
    empty = main.RECONSTRUCTION_STORE.create(title="No parts", rightsAccepted=True)
    main.RECONSTRUCTION_STORE.save(empty)
    no_midi = client.get(f"/api/reconstructions/{empty.id}/export-midi")

    assert missing.status_code == 404
    assert no_midi.status_code == 400
```

> Note: confirm `isolated_client` rebinds `main.RECONSTRUCTION_STORE` (it does — it `monkeypatch.setattr(main, "RECONSTRUCTION_STORE", ...)`), so `main.RECONSTRUCTION_STORE` inside the test refers to the isolated store. Call `isolated_client(...)` **before** seeding.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_reconstruction_api.py -k export_midi -v`
Expected: FAIL — endpoint returns 404 for the seeded project (route not defined) / `AttributeError` on missing import.

- [ ] **Step 3: Implement the endpoint**

In `backend/app/main.py`, change the existing import:

```python
from .midi_export import payload_to_midi, song_to_midi
```

to:

```python
from .midi_export import payload_to_midi, reconstruction_to_midi, song_to_midi
```

Add the endpoint next to `export_reconstruction` (after the `/export` route, around line 791):

```python
@app.get("/api/reconstructions/{project_id}/export-midi")
def export_reconstruction_midi(project_id: str) -> Response:
    try:
        project = RECONSTRUCTION_STORE.get(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reconstruction project not found") from exc
    if not any(part.outputMode == "midi" for part in project.parts):
        raise HTTPException(status_code=400, detail="project has no MIDI parts to export")
    data = reconstruction_to_midi(project)
    filename = _safe_filename(project.title) or "reconstruction"
    return Response(
        content=data,
        media_type="audio/midi",
        headers={"Content-Disposition": f'attachment; filename="{filename}.mid"'},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_reconstruction_api.py -k export_midi -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_reconstruction_api.py
git commit -m "feat: add reconstruction multi-track MIDI export endpoint"
```

---

### Task 3: Sync planner (`reconstruction_sync.py` — pure)

**Files:**
- Create: `backend/app/reconstruction_sync.py`
- Test: `backend/tests/test_reconstruction_sync.py`

**Interfaces:**
- Consumes: `reconstruction_contracts.ReconstructionProject`; `contracts.BridgeSnapshot`.
- Produces:
  - `@dataclass SyncAssignment(index: int, name: str)` with `to_dict()`.
  - `@dataclass SyncSkip(kind: str, name: str, message: str)` with `to_dict()`.
  - `@dataclass SyncPlan(tempo: int | None, channels: list[SyncAssignment], mixer: list[SyncAssignment], skipped: list[SyncSkip])` with `is_empty() -> bool` and `fl_code() -> str`.
  - `build_sync_plan(project: ReconstructionProject, snapshot: BridgeSnapshot) -> SyncPlan`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_reconstruction_sync.py`:

```python
from app.contracts import BridgeSnapshot, Note, NotePayload
from app.reconstruction_contracts import (
    AnalysisSummary,
    PatternSlice,
    ReconstructedPart,
    ReconstructionProject,
)
from app.reconstruction_sync import build_sync_plan


def _connected_snapshot(channel_count, track_count):
    return BridgeSnapshot.from_dict(
        {
            "status": "connected",
            "message": "ok",
            "source": "flapi",
            "trackCount": track_count,
            "channelCount": channel_count,
            "transport": {
                "playing": False, "recording": False, "loopMode": 0,
                "songPosition": 0.0, "songPositionHint": "", "songLengthBars": None, "tempo": 120.0,
            },
            "tracks": [], "channels": [], "setup": [], "errors": [],
        }
    )


def _project_with_parts(part_count):
    project = ReconstructionProject.create(title="Rebuild", rightsAccepted=True)
    parts = []
    for i in range(part_count):
        payload = NotePayload.create(
            title=f"Part {i}", sourcePrompt="Reconstructed", genre="South African dance",
            bpm=112, key="G", scale="minor", bars=1, notes=[Note(40 + i, 0.0, 1.0, 0.8)],
        )
        parts.append(
            ReconstructedPart.create(
                sourceStemId=f"stem-{i}", name=f"Part {i}", role="bass",
                outputMode="midi", confidence=0.9,
                patterns=[PatternSlice.create(name=f"Part {i}", startBar=1, payload=payload)],
            )
        )
    summary = AnalysisSummary.from_dict(
        {"bpm": 112, "bpmConfidence": 0.8, "key": "G", "scale": "minor",
         "keyConfidence": 0.8, "timeSignature": "4/4", "durationSeconds": 8.0,
         "integratedLoudness": None, "peakDb": None, "stereoWidth": None, "sections": []}
    )
    return project.with_changes(analysisSummary=summary, parts=parts)


def test_build_sync_plan_maps_parts_to_channels_and_mixer():
    project = _project_with_parts(2)
    plan = build_sync_plan(project, _connected_snapshot(channel_count=5, track_count=125))

    assert plan.tempo == 112
    assert [(a.index, a.name) for a in plan.channels] == [(0, "Part 0"), (1, "Part 1")]
    assert [(a.index, a.name) for a in plan.mixer] == [(1, "Part 0"), (2, "Part 1")]
    assert plan.skipped == []
    assert plan.is_empty() is False


def test_build_sync_plan_skips_parts_beyond_channel_count():
    project = _project_with_parts(3)
    plan = build_sync_plan(project, _connected_snapshot(channel_count=1, track_count=125))

    assert [a.index for a in plan.channels] == [0]
    skipped_channels = [s for s in plan.skipped if s.kind == "channel"]
    assert [s.name for s in skipped_channels] == ["Part 1", "Part 2"]


def test_fl_code_emits_tempo_and_name_writes():
    project = _project_with_parts(1)
    plan = build_sync_plan(project, _connected_snapshot(channel_count=1, track_count=125))
    code = plan.fl_code()

    assert "general.processRECEvent(midi.REC_Tempo, 112000," in code
    assert 'channels.setChannelName(0, "Part 0", useGlobalIndex=True)' in code
    assert 'mixer.setTrackName(1, "Part 0")' in code
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_reconstruction_sync.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.reconstruction_sync'`.

- [ ] **Step 3: Implement the planner**

Create `backend/app/reconstruction_sync.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .contracts import BridgeSnapshot
from .reconstruction_contracts import ReconstructionProject


@dataclass(frozen=True)
class SyncAssignment:
    index: int
    name: str

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "name": self.name}


@dataclass(frozen=True)
class SyncSkip:
    kind: str
    name: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "name": self.name, "message": self.message}


@dataclass(frozen=True)
class SyncPlan:
    tempo: int | None
    channels: list[SyncAssignment]
    mixer: list[SyncAssignment]
    skipped: list[SyncSkip]

    def is_empty(self) -> bool:
        return self.tempo is None and not self.channels and not self.mixer

    def fl_code(self) -> str:
        lines: list[str] = []
        if self.tempo is not None:
            value = int(round(self.tempo * 1000))
            lines.append("import general")
            lines.append("import midi")
            lines.append(
                f"general.processRECEvent(midi.REC_Tempo, {value}, "
                "midi.REC_Control | midi.REC_UpdateControl)"
            )
        if self.channels:
            lines.append("import channels")
            for item in self.channels:
                lines.append(
                    f"channels.setChannelName({item.index}, {json.dumps(item.name)}, useGlobalIndex=True)"
                )
        if self.mixer:
            lines.append("import mixer")
            for item in self.mixer:
                lines.append(f"mixer.setTrackName({item.index}, {json.dumps(item.name)})")
        return "\n".join(lines)


def build_sync_plan(project: ReconstructionProject, snapshot: BridgeSnapshot) -> SyncPlan:
    midi_parts = [part for part in project.parts if part.outputMode == "midi"]
    tempo = round(project.analysisSummary.bpm) if project.analysisSummary else None
    channel_count = snapshot.channelCount or 0
    track_count = snapshot.trackCount or 0
    channels: list[SyncAssignment] = []
    mixer: list[SyncAssignment] = []
    skipped: list[SyncSkip] = []
    for index, part in enumerate(midi_parts):
        if index < channel_count:
            channels.append(SyncAssignment(index=index, name=part.name))
        else:
            skipped.append(
                SyncSkip(
                    kind="channel",
                    name=part.name,
                    message=f"No channel at index {index} yet — add more channels in FL, then sync again.",
                )
            )
        insert = index + 1
        if insert <= track_count:
            mixer.append(SyncAssignment(index=insert, name=part.name))
        else:
            skipped.append(
                SyncSkip(
                    kind="mixer",
                    name=part.name,
                    message=f"No mixer insert at index {insert} yet.",
                )
            )
    return SyncPlan(tempo=tempo, channels=channels, mixer=mixer, skipped=skipped)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_reconstruction_sync.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/reconstruction_sync.py backend/tests/test_reconstruction_sync.py
git commit -m "feat: add pure reconstruction-to-FL sync planner"
```

---

### Task 4: Sync orchestrator + `POST /api/reconstructions/{id}/sync-fl`

**Files:**
- Modify: `backend/app/reconstruction_sync.py` (add `apply_reconstruction_sync`)
- Modify: `backend/app/main.py` (import + endpoint)
- Test: `backend/tests/test_reconstruction_sync.py` (orchestrator with fake client)
- Test: `backend/tests/test_reconstruction_api.py` (endpoint route)

**Interfaces:**
- Consumes: `bridge.probe_bridge`, `bridge.run_bridge_write` (existing, accept `client_factory`); `build_sync_plan` (Task 3); `main.RECONSTRUCTION_STORE`.
- Produces:
  - `apply_reconstruction_sync(project: ReconstructionProject, client_factory=None) -> dict[str, Any]` — probes the bridge, builds the plan, applies one combined write, returns a report dict with keys `connected: bool`, `message: str`, `tempo: {value, status} | None`, `channels: [{index, name, status}]`, `mixer: [{index, name, status}]`, `skipped: [{kind, name, message}]`, `bridge: <snapshot dict>`.
  - `POST /api/reconstructions/{project_id}/sync-fl` → that report dict; `404` unknown project.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_reconstruction_sync.py` a fake-client orchestrator test (the fake mirrors `test_bridge.py`'s pattern — `exec`/`eval`/`close`, returning a connected snapshot with the given counts):

```python
def _fake_client_factory(channel_count, track_count, recorder):
    class FakeClient:
        def exec(self, code):
            recorder.append(code)

        def eval(self, expression):
            values = {
                '__fl_connector_bridge_snapshot__["flVersion"]': "v2025",
                '__fl_connector_bridge_snapshot__["projectTitle"]': "Rebuild",
                '__fl_connector_bridge_snapshot__["selectedTrack"]': 0,
                '__fl_connector_bridge_snapshot__["trackCount"]': track_count,
                '__fl_connector_bridge_snapshot__["transport"]': {
                    "playing": False, "recording": False, "loopMode": 0,
                    "songPosition": 0.0, "songPositionHint": "", "songLengthBars": None, "tempo": 120.0,
                },
                'len(__fl_connector_bridge_snapshot__["tracks"])': 0,
                '__fl_connector_bridge_snapshot__["channelCount"]': channel_count,
                '__fl_connector_bridge_snapshot__["selectedChannel"]': 0,
                'len(__fl_connector_bridge_snapshot__["channels"])': 0,
                '__fl_connector_bridge_snapshot__["errors"]': [],
            }
            return values[expression]

        def close(self):
            pass

    return FakeClient


def test_apply_reconstruction_sync_applies_writes_and_reports():
    from app.reconstruction_sync import apply_reconstruction_sync

    project = _project_with_parts(2)
    recorder = []
    report = apply_reconstruction_sync(
        project, client_factory=_fake_client_factory(5, 125, recorder)
    )

    assert report["connected"] is True
    assert report["tempo"] == {"value": 112, "status": "applied"}
    assert [c["name"] for c in report["channels"]] == ["Part 0", "Part 1"]
    assert all(c["status"] == "applied" for c in report["channels"])
    # the combined write code was executed at least once
    assert any("setChannelName(0" in code for code in recorder)


def test_apply_reconstruction_sync_reports_disconnected():
    from app.reconstruction_sync import apply_reconstruction_sync

    project = _project_with_parts(1)

    def missing_client():
        raise ModuleNotFoundError("No module named 'flapi'")

    report = apply_reconstruction_sync(project, client_factory=missing_client)
    assert report["connected"] is False
    assert report["channels"] == []
```

Add to `backend/tests/test_reconstruction_api.py` (reuses `_seed_midi_project` from Task 2):

```python
def test_sync_fl_endpoint_returns_report(tmp_path, monkeypatch):
    client = isolated_client(tmp_path, monkeypatch)
    project = _seed_midi_project(main.RECONSTRUCTION_STORE)

    # bridge not connected in the test environment -> a clean disconnected report, not a 500
    response = client.post(f"/api/reconstructions/{project.id}/sync-fl")
    assert response.status_code == 200
    assert response.json()["connected"] is False


def test_sync_fl_endpoint_404_for_unknown(tmp_path, monkeypatch):
    client = isolated_client(tmp_path, monkeypatch)
    response = client.post("/api/reconstructions/nope/sync-fl")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_reconstruction_sync.py::test_apply_reconstruction_sync_applies_writes_and_reports tests/test_reconstruction_api.py -k sync_fl -v`
Expected: FAIL — `apply_reconstruction_sync` not defined / route missing (404 on the seeded project).

- [ ] **Step 3: Implement the orchestrator and endpoint**

Add to the top imports of `backend/app/reconstruction_sync.py`:

```python
from collections.abc import Callable

from .bridge import probe_bridge, run_bridge_write
```

Append to `backend/app/reconstruction_sync.py`:

```python
def _status_items(items: list[SyncAssignment], status: str) -> list[dict[str, Any]]:
    return [{"index": item.index, "name": item.name, "status": status} for item in items]


def apply_reconstruction_sync(
    project: ReconstructionProject,
    client_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    snapshot = probe_bridge(client_factory)
    if snapshot.status != "connected":
        return {
            "connected": False,
            "message": snapshot.message,
            "tempo": None,
            "channels": [],
            "mixer": [],
            "skipped": [],
            "bridge": snapshot.to_dict(),
        }
    plan = build_sync_plan(project, snapshot)
    if plan.is_empty():
        return {
            "connected": True,
            "message": "Nothing to sync yet — add channels/mixer tracks in FL, then sync again.",
            "tempo": None,
            "channels": [],
            "mixer": [],
            "skipped": [skip.to_dict() for skip in plan.skipped],
            "bridge": snapshot.to_dict(),
        }
    result = run_bridge_write(
        plan.fl_code(),
        "Synced FL session to the reconstruction.",
        client_factory,
    )
    status = "applied" if result.status == "connected" else "failed"
    return {
        "connected": True,
        "message": result.message,
        "tempo": {"value": plan.tempo, "status": status} if plan.tempo is not None else None,
        "channels": _status_items(plan.channels, status),
        "mixer": _status_items(plan.mixer, status),
        "skipped": [skip.to_dict() for skip in plan.skipped],
        "bridge": result.to_dict(),
    }
```

In `backend/app/main.py`, add the import (near the other reconstruction imports, e.g. after `from .reconstruction_export import build_reconstruction_export`):

```python
from .reconstruction_sync import apply_reconstruction_sync
```

Add the endpoint after `export_reconstruction_midi`:

```python
@app.post("/api/reconstructions/{project_id}/sync-fl")
def sync_reconstruction_to_fl(project_id: str) -> dict[str, Any]:
    try:
        project = RECONSTRUCTION_STORE.get(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reconstruction project not found") from exc
    return apply_reconstruction_sync(project)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_reconstruction_sync.py tests/test_reconstruction_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/reconstruction_sync.py backend/app/main.py backend/tests/test_reconstruction_sync.py backend/tests/test_reconstruction_api.py
git commit -m "feat: add reconstruction sync-fl orchestrator and endpoint"
```

---

### Task 5: Rewrite guide steps to the new loop

**Files:**
- Modify: `backend/app/reconstruction_compiler.py` (`_guide_steps` rows)
- Test: `backend/tests/test_reconstruction_compiler.py` (add an assertion for the new flow)

**Interfaces:**
- Consumes/Produces: `ReconstructionCompiler._guide_steps()` still returns `list[GuideStep]`; only the row content changes. `imageAsset` paths stay under `/guides/fl-2025/`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_reconstruction_compiler.py`:

```python
def test_guide_steps_describe_the_send_to_fl_loop():
    from app.reconstruction_compiler import ReconstructionCompiler

    steps = ReconstructionCompiler()._guide_steps()
    titles = [step.title for step in steps]

    assert any("arrangement MIDI" in title for title in titles)
    assert any("Sync FL" in title for title in titles)
    assert all(step.imageAsset.startswith("/guides/fl-2025/") for step in steps)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_reconstruction_compiler.py -k send_to_fl_loop -v`
Expected: FAIL — no step title contains "arrangement MIDI".

- [ ] **Step 3: Replace the `rows` in `_guide_steps`**

In `backend/app/reconstruction_compiler.py`, replace the `rows = [ ... ]` list inside `_guide_steps()` with:

```python
        rows = [
            (
                "Import the arrangement MIDI",
                "Playlist",
                "Download the arrangement MIDI and drag it onto the Playlist; let FL split it into one channel per part.",
                "Send to FL > Download arrangement MIDI, then drag into View > Playlist",
                "F5",
                "/guides/fl-2025/playlist.svg",
                "Reconstructed parts appear as channels and pattern clips.",
            ),
            (
                "Sync FL to this rebuild",
                "Channel Rack",
                "Click Sync FL to this rebuild to set the tempo and rename the channels and mixer tracks to match.",
                "Send to FL > Sync FL to this rebuild",
                None,
                "/guides/fl-2025/channel-rack.svg",
                "Tempo matches the analysis and channels are named after each part.",
            ),
            (
                "Add instruments and plugins",
                "Channel Rack",
                "Load the approved instrument into each named channel and insert any plugins (this stays manual).",
                "Channel Rack > channel > select the approved instrument",
                None,
                "/guides/fl-2025/add-instrument.svg",
                "Each channel plays through the chosen instrument.",
            ),
            (
                "Apply the mix plan",
                "Mixer",
                "Route each channel to its mixer track and add the approved built-in effects from the mix plan.",
                "View > Mixer",
                "F9",
                "/guides/fl-2025/mixer.svg",
                "Each part has its own Mixer track with the listed effects.",
            ),
            (
                "Check the arrangement",
                "Playlist",
                "Confirm the pattern clips line up with the blueprint sections.",
                "View > Playlist",
                "F5",
                "/guides/fl-2025/playlist.svg",
                "Patterns line up with the arrangement sections.",
            ),
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_reconstruction_compiler.py -v`
Expected: PASS (the new test plus the existing `imageAsset` assertion at line 75).

- [ ] **Step 5: Commit**

```bash
git add backend/app/reconstruction_compiler.py backend/tests/test_reconstruction_compiler.py
git commit -m "feat: rewrite reconstruction guide steps for the send-to-FL loop"
```

---

### Task 6: Embed the spine in the export ZIP

**Files:**
- Modify: `backend/app/reconstruction_export.py` (add `arrangement.mid`)
- Test: `backend/tests/test_reconstruction_export.py` (assert the new entry; keep the per-pattern assertion)

**Interfaces:**
- Consumes: `midi_export.reconstruction_to_midi` (Task 1).
- Produces: ZIP additionally contains `arrangement.mid` when the project has MIDI parts. Existing `midi/<part>/<pattern>.mid` entries are unchanged.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_reconstruction_export.py`:

```python
def test_export_zip_contains_full_arrangement_spine(tmp_path):
    from app.reconstruction_export import build_reconstruction_export

    project = _project()  # the existing helper in this file that has a MIDI part
    bundle_bytes = build_reconstruction_export(project, tmp_path)
    from io import BytesIO
    from zipfile import ZipFile

    with ZipFile(BytesIO(bundle_bytes)) as bundle:
        names = set(bundle.namelist())
    assert "arrangement.mid" in names
    assert "midi/Bass/Bass A.mid" in names  # per-pattern files still present
```

> If the existing project-builder in this test file is not named `_project`, reuse whatever fixture/helper `test_export_zip_contains_project_midi_and_reports` already uses to construct its project (same object).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_reconstruction_export.py -k spine -v`
Expected: FAIL — `arrangement.mid` not in the zip.

- [ ] **Step 3: Implement the spine entry**

In `backend/app/reconstruction_export.py`, add to the imports:

```python
from .midi_export import reconstruction_to_midi
```

In `build_reconstruction_export`, after the `archive.writestr("guide-manifest.json", ...)` block and before the `for part in project.parts:` loop, add:

```python
        if any(part.outputMode == "midi" for part in project.parts):
            archive.writestr("arrangement.mid", reconstruction_to_midi(project))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_reconstruction_export.py -v`
Expected: PASS (new spine test plus the existing per-pattern/report test).

- [ ] **Step 5: Commit**

```bash
git add backend/app/reconstruction_export.py backend/tests/test_reconstruction_export.py
git commit -m "feat: include full arrangement MIDI spine in reconstruction export"
```

---

### Task 7: Frontend "Send to FL" card

**Files:**
- Modify: `frontend/src/api.js` (two client methods)
- Modify: `frontend/src/reconstruction/ReconstructionWorkspace.jsx` (import `Send`; add `SendToFl` + `SyncReportView`; render the card)
- Test: `frontend/src/reconstruction/ReconstructionWorkspace.test.jsx` (extend `clientFor`; add a test)

**Interfaces:**
- Consumes: backend endpoints from Tasks 2 & 4.
- Produces: `api.exportReconstructionMidi(id)` (browser download) and `api.syncReconstructionToFl(id)` (POST → report). A `SendToFl` section rendered in the workspace.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/reconstruction/ReconstructionWorkspace.test.jsx`. First extend the `clientFor` factory's returned object with the two new mocks (add these lines alongside `exportReconstruction: vi.fn(),`):

```javascript
    exportReconstructionMidi: vi.fn(),
    syncReconstructionToFl: vi.fn().mockResolvedValue({
      connected: true,
      message: 'Synced FL session to the reconstruction.',
      tempo: { value: 112, status: 'applied' },
      channels: [{ index: 0, name: 'Bass', status: 'applied' }],
      mixer: [{ index: 1, name: 'Bass', status: 'applied' }],
      skipped: [],
    }),
```

Then add the test:

```javascript
test('sends the rebuild to FL via MIDI download and bridge sync', async () => {
  const project = draftProject({
    status: 'review',
    parts: [
      {
        id: 'part-1', sourceStemId: 'stem-1', name: 'Bass', role: 'bass',
        outputMode: 'midi', confidence: 0.9, requiresReview: false, instrumentHint: 'BooBass',
        patterns: [], audioRelativePath: null, audioStartSeconds: 0,
        selectedSoundId: null, warnings: [], approved: false,
      },
    ],
  });
  const client = clientFor([project]);

  render(<ReconstructionWorkspace client={client} />);

  const download = await screen.findByRole('button', { name: /Download arrangement MIDI/i });
  fireEvent.click(download);
  expect(client.exportReconstructionMidi).toHaveBeenCalledWith('project-1');

  fireEvent.click(screen.getByRole('button', { name: /Sync FL to this rebuild/i }));
  await waitFor(() => expect(client.syncReconstructionToFl).toHaveBeenCalledWith('project-1'));
  expect(await screen.findByText(/1 channel named/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run ReconstructionWorkspace`
Expected: FAIL — no "Download arrangement MIDI" button rendered.

- [ ] **Step 3: Add the API methods**

In `frontend/src/api.js`, add after the `exportReconstruction` line (line ~88):

```javascript
  exportReconstructionMidi: (id) => download(`/api/reconstructions/${id}/export-midi`, `rebuild-${id}.mid`),
  syncReconstructionToFl: (id) => request(`/api/reconstructions/${id}/sync-fl`, { method: 'POST' }),
```

- [ ] **Step 4: Add the component and render it**

In `frontend/src/reconstruction/ReconstructionWorkspace.jsx`, add `Send` to the `lucide-react` import list (alongside `Download`, `RefreshCw`, which are already imported).

Add these two components near the other section components (e.g. after `MixPlan`):

```jsx
function SyncReportView({ report }) {
  if (!report.connected) {
    return <div className="sync-report disconnected">FL not connected: {report.message}</div>;
  }
  return (
    <div className="sync-report">
      {report.tempo && <p>Tempo set to {report.tempo.value} BPM ({report.tempo.status}).</p>}
      <p>
        {report.channels.length} channel{report.channels.length === 1 ? '' : 's'} named,{' '}
        {report.mixer.length} mixer track{report.mixer.length === 1 ? '' : 's'} named.
      </p>
      {report.skipped.length > 0 && (
        <ul className="sync-skipped">
          {report.skipped.map((skip, index) => (
            <li key={`${skip.kind}-${index}`}>{skip.message}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SendToFl({ project, client, busy, onError }) {
  const [report, setReport] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const hasMidi = project.parts.some((part) => part.outputMode === 'midi');

  async function sync() {
    setSyncing(true);
    onError('');
    try {
      setReport(await client.syncReconstructionToFl(project.id));
    } catch (reason) {
      onError(reason.message);
    } finally {
      setSyncing(false);
    }
  }

  return (
    <section className="rebuild-section send-to-fl">
      <header><div><p>Send to FL</p><h2>One-drag handoff</h2></div><Send size={20} /></header>
      <div className="send-to-fl-actions">
        <button
          className="primary-button rebuild-inline"
          disabled={busy || !hasMidi}
          onClick={() => client.exportReconstructionMidi(project.id)}
        >
          <Download size={17} /> Download arrangement MIDI
        </button>
        <button
          className="secondary-button rebuild-inline"
          disabled={busy || syncing}
          onClick={sync}
        >
          <RefreshCw size={17} /> Sync FL to this rebuild
        </button>
      </div>
      <p className="rebuild-muted">
        Drag the MIDI onto the FL Playlist, then click Sync to set tempo and name the channels.
      </p>
      {report && <SyncReportView report={report} />}
    </section>
  );
}
```

Render it in the main workspace JSX — add this line immediately after `<Arrangement project={project} />` (around line 551):

```jsx
          <SendToFl project={project} client={client} busy={busy} onError={setError} />
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test -- --run ReconstructionWorkspace`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api.js frontend/src/reconstruction/ReconstructionWorkspace.jsx frontend/src/reconstruction/ReconstructionWorkspace.test.jsx
git commit -m "feat: add Send to FL card with MIDI download and bridge sync"
```

---

### Task 8: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full backend suite**

Run: `cd backend && python -m pytest -q`
Expected: PASS — all tests (was 145 at the start of Phase 4; new tests add to that).

- [ ] **Step 2: Run the full frontend suite and build**

Run: `cd frontend && npm test -- --run && npm run build`
Expected: tests PASS, build succeeds.

- [ ] **Step 3: Commit any incidental fixes**

If a cross-file regression surfaced, fix it minimally and commit:

```bash
git add -A
git commit -m "test: fix Phase 4 regressions surfaced by full suite"
```

---

## Self-Review

**Spec coverage:**
- One-drag multi-track MIDI builder → Task 1; endpoint → Task 2. ✓
- Server-side sync planner (Approach A, pure) → Task 3; orchestrator + `/sync-fl` endpoint with synced/skipped report and disconnected handling → Task 4. ✓
- Tempo + channel names + mixer names only, via existing bridge writes, global indexing → Tasks 3–4 (`fl_code`, `build_sync_plan`). ✓
- Updated guide steps → Task 5. ✓
- ZIP keeps per-pattern files and gains the spine → Task 6. ✓
- Frontend "Send to FL" card + two api methods, ZIP export retained (untouched) → Task 7. ✓
- Audio parts excluded from MIDI; out-of-scope items (analysis accuracy, status machine, numeric levels) not touched. ✓
- Error handling: export-midi 404/400 (Task 2); sync-fl 404 + disconnected-as-200 (Task 4). ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code and exact commands. The one soft reference (Task 6 "reuse the existing project helper") names the exact alternative and the concrete assertion it must satisfy.

**Type consistency:** `reconstruction_to_midi(project) -> bytes` is defined in Task 1 and consumed identically in Tasks 2 and 6. `build_sync_plan(project, snapshot) -> SyncPlan` (Task 3) is consumed by `apply_reconstruction_sync` (Task 4). The report dict keys (`connected`, `tempo{value,status}`, `channels[{index,name,status}]`, `mixer`, `skipped[{kind,name,message}]`) are produced in Task 4 and consumed verbatim by `SyncReportView` in Task 7. `SyncAssignment`/`SyncSkip`/`SyncPlan` names match across Tasks 3–4.

## Post-build: live-FL acceptance (user-run)

1. Generate/seed a reconstruction with MIDI parts → click **Download arrangement MIDI** → drag into FL → verify one track per MIDI part at correct bars, full length.
2. With FL + Flapi live, click **Sync FL to this rebuild** → verify tempo moves to the detected BPM, channels and mixer tracks rename to the part names in order, and the report lists "add more channels" correctly when there are fewer channels than parts.
3. Confirm the part *i* ↔ channel *i* ordering holds after the MIDI drag (the one ordering risk).
