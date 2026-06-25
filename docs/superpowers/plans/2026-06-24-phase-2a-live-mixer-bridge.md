# Phase 2a — Live Mixer + Transport Writes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the read-only Flapi bridge with reversible live writes — project tempo sync and per mixer-track name/volume/pan/select/mute/solo — each behind an explicit per-action Apply in the UI.

**Architecture:** A single `run_bridge_write(fl_code, message)` helper (factored out of the existing `run_transport_action`) runs a one-line FL script inside FL via Flapi, re-runs the read-only probe, and returns a fresh `BridgeSnapshot`. Typed write functions build the FL code; thin FastAPI endpoints expose them; the React Bridge panel gets per-track controls.

**Tech Stack:** Python 3.11 / FastAPI / pytest (backend venv at `backend/.venv`); React 18 / Vite / Vitest / @testing-library/react (frontend).

## Global Constraints

- Working dir: `C:\Users\HP\Vocals APP\fl-connector`. Branch: `phase-2a-live-mixer-bridge` (already created, spec committed).
- Backend test command: `cd backend && ./.venv/Scripts/python -m pytest -q`. Frontend: `cd frontend && npm test`; build `npm run build`.
- The read-only probe `READ_ONLY_FL_PROBE` must stay free of write calls — `test_read_only_probe_does_not_include_write_actions` must keep passing.
- Mute/solo are **toggles** (FL `muteTrack(index)`/`soloTrack(index)` with no value toggle), because the snapshot does not carry mute/solo state. This refines the spec's `{on}` shape.
- FL volume scale is 0–1 (~0.8 = unity). Track index range 0–125. BPM 40–240. Name ≤ 100 chars.
- The exact FL scripting calls (`general.processRECEvent(midi.REC_Tempo, …)`, `mixer.setTrackName/Volume/Pan/Number`, `muteTrack`, `soloTrack`) are verified by **live acceptance** (Task 7); unit tests use an injected fake client and assert the exact code string emitted, so they do not depend on a running FL.
- Each FL code string interpolates only validated numbers and a `json.dumps`-encoded name (injection-safe).
- Plugin insertion and note placement are NOT in scope (API cannot do them).

**Spec:** `docs/superpowers/specs/2026-06-24-phase-2a-live-mixer-bridge-design.md`

---

## Task 1: `run_bridge_write` helper + transport refactor

**Files:**
- Modify: `backend/app/bridge.py`
- Test: `backend/tests/test_bridge.py`

**Interfaces:**
- Produces: `run_bridge_write(fl_code: str, message: str, client_factory: Callable[[], Any] | None = None) -> BridgeSnapshot` — acquires the bridge lock, connects, `exec`s `fl_code`, re-runs the read-only probe, returns a `connected` snapshot with `message`; returns `disconnected`/`error` snapshots on failure.
- Consumes: existing `_BRIDGE_PROBE_LOCK`, `default_client_factory`, `READ_ONLY_FL_PROBE`, `_read_bridge_snapshot`, `_connected_snapshot`, `_disconnected`, `_error`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_bridge.py`:

```python
def test_run_bridge_write_execs_code_then_probe_and_returns_snapshot():
    calls = []

    class FakeClient:
        def exec(self, code):
            calls.append(("exec", code))

        def eval(self, expression):
            values = {
                '__fl_connector_bridge_snapshot__["flVersion"]': "Producer Edition v2025",
                '__fl_connector_bridge_snapshot__["projectTitle"]': "Write project",
                '__fl_connector_bridge_snapshot__["selectedTrack"]': 0,
                '__fl_connector_bridge_snapshot__["trackCount"]': 0,
                '__fl_connector_bridge_snapshot__["transport"]': {
                    "playing": False, "recording": False, "loopMode": 0,
                    "songPosition": 0.0, "songPositionHint": "", "songLengthBars": None, "tempo": None,
                },
                'len(__fl_connector_bridge_snapshot__["tracks"])': 0,
                '__fl_connector_bridge_snapshot__["errors"]': [],
            }
            return values[expression]

        def close(self):
            calls.append(("close", None))

    from app.bridge import run_bridge_write, READ_ONLY_FL_PROBE

    snapshot = run_bridge_write("import mixer\nmixer.setTrackName(1, \"x\")", "done", client_factory=FakeClient)

    assert snapshot.status == "connected"
    assert snapshot.message == "done"
    assert calls == [
        ("exec", "import mixer\nmixer.setTrackName(1, \"x\")"),
        ("exec", READ_ONLY_FL_PROBE),
        ("close", None),
    ]


def test_run_bridge_write_reports_disconnected_when_flapi_missing():
    from app.bridge import run_bridge_write

    def missing_client():
        raise ModuleNotFoundError("No module named 'flapi'")

    snapshot = run_bridge_write("x = 1", "done", client_factory=missing_client)
    assert snapshot.status == "disconnected"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_bridge.py -q`
Expected: FAIL — `ImportError: cannot import name 'run_bridge_write'`.

- [ ] **Step 3: Add `run_bridge_write` and refactor `run_transport_action`**

In `backend/app/bridge.py`, replace the entire existing `run_transport_action` function with:

```python
def run_bridge_write(
    fl_code: str,
    message: str,
    client_factory: Callable[[], Any] | None = None,
) -> BridgeSnapshot:
    factory = client_factory or default_client_factory
    client: Any | None = None
    with _BRIDGE_PROBE_LOCK:
        try:
            client = factory()
        except ModuleNotFoundError as exc:
            return _disconnected(
                "Flapi Python package is not importable in this backend environment.",
                [str(exc)],
            )
        except Exception as exc:
            return _disconnected(
                "Flapi could not connect to FL Studio. Check MIDI ports and controller scripts.",
                [str(exc)],
            )

        try:
            client.exec(fl_code)
            client.exec(READ_ONLY_FL_PROBE)
            raw_snapshot = _read_bridge_snapshot(client)
            return _connected_snapshot(message, raw_snapshot)
        except Exception as exc:
            return _error(
                "Flapi connected, but the live write action failed.",
                [str(exc)],
            )
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()


def run_transport_action(
    action: str,
    client_factory: Callable[[], Any] | None = None,
) -> BridgeSnapshot:
    command = TRANSPORT_ACTIONS.get(action)
    if command is None:
        raise ValueError(f"unsupported transport action: {action}")
    return run_bridge_write(
        f"import transport\n{command}",
        f"Live FL transport action applied: {action}.",
        client_factory=client_factory,
    )
```

- [ ] **Step 4: Run to verify it passes (and transport tests still pass)**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_bridge.py -q`
Expected: PASS — the two new tests plus all existing transport tests (the refactored `run_transport_action` still emits `("exec", "import transport\ntransport.start()")` then the probe).

- [ ] **Step 5: Commit**

```bash
git add backend/app/bridge.py backend/tests/test_bridge.py
git commit -m "refactor: add run_bridge_write helper behind run_transport_action

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `set_project_tempo`

**Files:**
- Modify: `backend/app/bridge.py`
- Test: `backend/tests/test_bridge.py`

**Interfaces:**
- Produces: `set_project_tempo(bpm: float, client_factory=None) -> BridgeSnapshot`. Raises `ValueError` if `bpm` not in 40–240.
- Consumes: `run_bridge_write` (Task 1).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_bridge.py`:

```python
def test_set_project_tempo_emits_rec_event_and_validates():
    import pytest
    from app.bridge import set_project_tempo

    captured = {}

    class FakeClient:
        def exec(self, code):
            captured.setdefault("code", code)

        def eval(self, expression):
            values = {
                '__fl_connector_bridge_snapshot__["flVersion"]': "v2025",
                '__fl_connector_bridge_snapshot__["projectTitle"]': "Tempo",
                '__fl_connector_bridge_snapshot__["selectedTrack"]': 0,
                '__fl_connector_bridge_snapshot__["trackCount"]': 0,
                '__fl_connector_bridge_snapshot__["transport"]': {
                    "playing": False, "recording": False, "loopMode": 0,
                    "songPosition": 0.0, "songPositionHint": "", "songLengthBars": None, "tempo": 120.0,
                },
                'len(__fl_connector_bridge_snapshot__["tracks"])': 0,
                '__fl_connector_bridge_snapshot__["errors"]': [],
            }
            return values[expression]

        def close(self):
            pass

    snapshot = set_project_tempo(120, client_factory=FakeClient)
    assert snapshot.status == "connected"
    assert captured["code"] == (
        "import general\n"
        "import midi\n"
        "general.processRECEvent(midi.REC_Tempo, 120000, midi.REC_Control | midi.REC_UpdateControl)"
    )

    with pytest.raises(ValueError):
        set_project_tempo(20, client_factory=FakeClient)
    with pytest.raises(ValueError):
        set_project_tempo(500, client_factory=FakeClient)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_bridge.py::test_set_project_tempo_emits_rec_event_and_validates -q`
Expected: FAIL — `ImportError: cannot import name 'set_project_tempo'`.

- [ ] **Step 3: Implement**

In `backend/app/bridge.py`, add after `run_transport_action`:

```python
def set_project_tempo(
    bpm: float,
    client_factory: Callable[[], Any] | None = None,
) -> BridgeSnapshot:
    if not 40 <= bpm <= 240:
        raise ValueError("bpm must be between 40 and 240")
    value = int(round(bpm * 1000))
    fl_code = (
        "import general\n"
        "import midi\n"
        f"general.processRECEvent(midi.REC_Tempo, {value}, midi.REC_Control | midi.REC_UpdateControl)"
    )
    return run_bridge_write(fl_code, f"Set FL project tempo to {bpm:g} BPM.", client_factory=client_factory)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_bridge.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/bridge.py backend/tests/test_bridge.py
git commit -m "feat: add live FL tempo write via REC_Tempo

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `set_mixer_track` (name / volume / pan)

**Files:**
- Modify: `backend/app/bridge.py`
- Test: `backend/tests/test_bridge.py`

**Interfaces:**
- Produces: `set_mixer_track(index: int, *, name: str | None = None, volume: float | None = None, pan: float | None = None, client_factory=None) -> BridgeSnapshot`. Raises `ValueError` if index not 0–125, no field given, name empty/>100, volume not 0–1, or pan not −1..1.
- Consumes: `run_bridge_write` (Task 1).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_bridge.py`:

```python
def test_set_mixer_track_builds_code_for_provided_fields():
    import pytest
    from app.bridge import set_mixer_track

    captured = {}

    class FakeClient:
        def exec(self, code):
            captured.setdefault("code", code)

        def eval(self, expression):
            values = {
                '__fl_connector_bridge_snapshot__["flVersion"]': "v2025",
                '__fl_connector_bridge_snapshot__["projectTitle"]': "Mix",
                '__fl_connector_bridge_snapshot__["selectedTrack"]': 0,
                '__fl_connector_bridge_snapshot__["trackCount"]': 0,
                '__fl_connector_bridge_snapshot__["transport"]': {
                    "playing": False, "recording": False, "loopMode": 0,
                    "songPosition": 0.0, "songPositionHint": "", "songLengthBars": None, "tempo": None,
                },
                'len(__fl_connector_bridge_snapshot__["tracks"])': 0,
                '__fl_connector_bridge_snapshot__["errors"]': [],
            }
            return values[expression]

        def close(self):
            pass

    snapshot = set_mixer_track(3, name='Lead "Bass"', volume=0.72, pan=-0.25, client_factory=FakeClient)
    assert snapshot.status == "connected"
    assert captured["code"] == (
        "import mixer\n"
        'mixer.setTrackName(3, "Lead \\"Bass\\"")\n'
        "mixer.setTrackVolume(3, 0.72)\n"
        "mixer.setTrackPan(3, -0.25)"
    )

    with pytest.raises(ValueError):
        set_mixer_track(3, client_factory=FakeClient)  # no fields
    with pytest.raises(ValueError):
        set_mixer_track(200, name="x", client_factory=FakeClient)  # index
    with pytest.raises(ValueError):
        set_mixer_track(3, volume=2.0, client_factory=FakeClient)  # volume
    with pytest.raises(ValueError):
        set_mixer_track(3, pan=5.0, client_factory=FakeClient)  # pan
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_bridge.py::test_set_mixer_track_builds_code_for_provided_fields -q`
Expected: FAIL — `ImportError: cannot import name 'set_mixer_track'`.

- [ ] **Step 3: Implement**

In `backend/app/bridge.py`, add `import json` to the top imports (alongside the existing imports) and add this function after `set_project_tempo`:

```python
def set_mixer_track(
    index: int,
    *,
    name: str | None = None,
    volume: float | None = None,
    pan: float | None = None,
    client_factory: Callable[[], Any] | None = None,
) -> BridgeSnapshot:
    if not 0 <= index <= 125:
        raise ValueError("mixer track index must be between 0 and 125")
    if name is None and volume is None and pan is None:
        raise ValueError("provide at least one of name, volume, or pan")
    lines = ["import mixer"]
    changed: list[str] = []
    if name is not None:
        if not name.strip() or len(name) > 100:
            raise ValueError("track name must be 1-100 characters")
        lines.append(f"mixer.setTrackName({index}, {json.dumps(name)})")
        changed.append("name")
    if volume is not None:
        if not 0 <= volume <= 1:
            raise ValueError("volume must be between 0 and 1")
        lines.append(f"mixer.setTrackVolume({index}, {round(volume, 4)})")
        changed.append("volume")
    if pan is not None:
        if not -1 <= pan <= 1:
            raise ValueError("pan must be between -1 and 1")
        lines.append(f"mixer.setTrackPan({index}, {round(pan, 4)})")
        changed.append("pan")
    message = f"Updated FL mixer track {index} ({', '.join(changed)})."
    return run_bridge_write("\n".join(lines), message, client_factory=client_factory)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_bridge.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/bridge.py backend/tests/test_bridge.py
git commit -m "feat: add live FL mixer track name/volume/pan write

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `select_mixer_track`, `set_mixer_track_mute`, `set_mixer_track_solo`

**Files:**
- Modify: `backend/app/bridge.py`
- Test: `backend/tests/test_bridge.py`

**Interfaces:**
- Produces: `select_mixer_track(index, client_factory=None)`, `set_mixer_track_mute(index, client_factory=None)`, `set_mixer_track_solo(index, client_factory=None)` — each `-> BridgeSnapshot`, each raises `ValueError` if index not 0–125. Mute/solo TOGGLE.
- Consumes: `run_bridge_write` (Task 1).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_bridge.py`:

```python
def test_select_mute_solo_emit_expected_code():
    import pytest
    from app.bridge import select_mixer_track, set_mixer_track_mute, set_mixer_track_solo

    def fake_factory(expected_first):
        class FakeClient:
            def exec(self, code):
                if not hasattr(self, "first"):
                    self.first = code
                    assert code == expected_first

            def eval(self, expression):
                values = {
                    '__fl_connector_bridge_snapshot__["flVersion"]': "v2025",
                    '__fl_connector_bridge_snapshot__["projectTitle"]': "T",
                    '__fl_connector_bridge_snapshot__["selectedTrack"]': 0,
                    '__fl_connector_bridge_snapshot__["trackCount"]': 0,
                    '__fl_connector_bridge_snapshot__["transport"]': {
                        "playing": False, "recording": False, "loopMode": 0,
                        "songPosition": 0.0, "songPositionHint": "", "songLengthBars": None, "tempo": None,
                    },
                    'len(__fl_connector_bridge_snapshot__["tracks"])': 0,
                    '__fl_connector_bridge_snapshot__["errors"]': [],
                }
                return values[expression]

            def close(self):
                pass

        return FakeClient

    assert select_mixer_track(2, client_factory=fake_factory("import mixer\nmixer.setTrackNumber(2)")).status == "connected"
    assert set_mixer_track_mute(2, client_factory=fake_factory("import mixer\nmixer.muteTrack(2)")).status == "connected"
    assert set_mixer_track_solo(2, client_factory=fake_factory("import mixer\nmixer.soloTrack(2)")).status == "connected"

    with pytest.raises(ValueError):
        select_mixer_track(999, client_factory=fake_factory(""))
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_bridge.py::test_select_mute_solo_emit_expected_code -q`
Expected: FAIL — `ImportError: cannot import name 'select_mixer_track'`.

- [ ] **Step 3: Implement**

In `backend/app/bridge.py`, add after `set_mixer_track`:

```python
def _require_track_index(index: int) -> None:
    if not 0 <= index <= 125:
        raise ValueError("mixer track index must be between 0 and 125")


def select_mixer_track(
    index: int, client_factory: Callable[[], Any] | None = None
) -> BridgeSnapshot:
    _require_track_index(index)
    return run_bridge_write(
        f"import mixer\nmixer.setTrackNumber({index})",
        f"Selected FL mixer track {index}.",
        client_factory=client_factory,
    )


def set_mixer_track_mute(
    index: int, client_factory: Callable[[], Any] | None = None
) -> BridgeSnapshot:
    _require_track_index(index)
    return run_bridge_write(
        f"import mixer\nmixer.muteTrack({index})",
        f"Toggled mute on FL mixer track {index}.",
        client_factory=client_factory,
    )


def set_mixer_track_solo(
    index: int, client_factory: Callable[[], Any] | None = None
) -> BridgeSnapshot:
    _require_track_index(index)
    return run_bridge_write(
        f"import mixer\nmixer.soloTrack({index})",
        f"Toggled solo on FL mixer track {index}.",
        client_factory=client_factory,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_bridge.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/bridge.py backend/tests/test_bridge.py
git commit -m "feat: add live FL mixer track select/mute/solo toggles

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Bridge write endpoints

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_bridge.py`

**Interfaces:**
- Consumes: `set_project_tempo`, `set_mixer_track`, `select_mixer_track`, `set_mixer_track_mute`, `set_mixer_track_solo` (Tasks 2–4).
- Produces: routes `POST /api/bridge/tempo`, `POST /api/bridge/mixer/{index}`, `POST /api/bridge/mixer/{index}/select`, `POST /api/bridge/mixer/{index}/mute`, `POST /api/bridge/mixer/{index}/solo`, each returning a `BridgeSnapshot` dict.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_bridge.py`:

```python
def test_bridge_write_endpoints_route_to_functions(monkeypatch):
    from app.contracts import BridgeSnapshot

    def fake_snapshot(message):
        return BridgeSnapshot.from_dict(
            {
                "status": "connected", "message": message, "source": "flapi",
                "flVersion": "v2025", "projectTitle": "P", "selectedTrack": 0, "trackCount": 0,
                "transport": {
                    "playing": False, "recording": False, "loopMode": 0,
                    "songPosition": 0.0, "songPositionHint": "", "songLengthBars": None, "tempo": 120.0,
                },
                "tracks": [], "setup": [], "errors": [],
            }
        )

    calls = []
    monkeypatch.setattr(main_module, "set_project_tempo", lambda bpm: calls.append(("tempo", bpm)) or fake_snapshot("t"))
    monkeypatch.setattr(main_module, "set_mixer_track", lambda index, name=None, volume=None, pan=None: calls.append(("mixer", index, name, volume, pan)) or fake_snapshot("m"))
    monkeypatch.setattr(main_module, "select_mixer_track", lambda index: calls.append(("select", index)) or fake_snapshot("s"))
    monkeypatch.setattr(main_module, "set_mixer_track_mute", lambda index: calls.append(("mute", index)) or fake_snapshot("mu"))
    monkeypatch.setattr(main_module, "set_mixer_track_solo", lambda index: calls.append(("solo", index)) or fake_snapshot("so"))

    assert main_module.bridge_set_tempo(main_module.BridgeTempoRequest(bpm=120))["status"] == "connected"
    assert main_module.bridge_set_mixer_track(3, main_module.BridgeMixerTrackRequest(name="Bass", volume=0.7, pan=0.0))["status"] == "connected"
    assert main_module.bridge_select_mixer_track(3)["status"] == "connected"
    assert main_module.bridge_mute_mixer_track(3)["status"] == "connected"
    assert main_module.bridge_solo_mixer_track(3)["status"] == "connected"

    assert calls == [
        ("tempo", 120.0),
        ("mixer", 3, "Bass", 0.7, 0.0),
        ("select", 3),
        ("mute", 3),
        ("solo", 3),
    ]


def test_bridge_set_tempo_maps_value_error_to_400(monkeypatch):
    import pytest
    from fastapi import HTTPException

    def boom(bpm):
        raise ValueError("bpm must be between 40 and 240")

    monkeypatch.setattr(main_module, "set_project_tempo", boom)
    with pytest.raises(HTTPException) as exc:
        main_module.bridge_set_tempo(main_module.BridgeTempoRequest(bpm=120))
    assert exc.value.status_code == 400
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_bridge.py::test_bridge_write_endpoints_route_to_functions -q`
Expected: FAIL — `AttributeError: module 'app.main' has no attribute 'bridge_set_tempo'`.

- [ ] **Step 3: Implement**

In `backend/app/main.py`, extend the bridge import:

```python
from .bridge import (
    probe_bridge,
    run_transport_action,
    select_mixer_track,
    set_mixer_track,
    set_mixer_track_mute,
    set_mixer_track_solo,
    set_project_tempo,
)
```

Add request models next to `BridgeTransportRequest`:

```python
class BridgeTempoRequest(BaseModel):
    bpm: float = Field(ge=40, le=240)


class BridgeMixerTrackRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    volume: float | None = Field(default=None, ge=0, le=1)
    pan: float | None = Field(default=None, ge=-1, le=1)
```

Add endpoints immediately after the existing `bridge_transport` endpoint:

```python
@app.post("/api/bridge/tempo")
def bridge_set_tempo(request: BridgeTempoRequest) -> dict[str, Any]:
    try:
        return set_project_tempo(request.bpm).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/bridge/mixer/{index}")
def bridge_set_mixer_track(index: int, request: BridgeMixerTrackRequest) -> dict[str, Any]:
    try:
        return set_mixer_track(
            index, name=request.name, volume=request.volume, pan=request.pan
        ).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/bridge/mixer/{index}/select")
def bridge_select_mixer_track(index: int) -> dict[str, Any]:
    try:
        return select_mixer_track(index).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/bridge/mixer/{index}/mute")
def bridge_mute_mixer_track(index: int) -> dict[str, Any]:
    try:
        return set_mixer_track_mute(index).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/bridge/mixer/{index}/solo")
def bridge_solo_mixer_track(index: int) -> dict[str, Any]:
    try:
        return set_mixer_track_solo(index).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- [ ] **Step 4: Run to verify it passes + full suite**

Run: `cd backend && ./.venv/Scripts/python -m pytest -q`
Expected: PASS (all existing + the new bridge tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_bridge.py
git commit -m "feat: expose live bridge write endpoints (tempo, mixer track ops)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Frontend bridge write controls

**Files:**
- Modify: `frontend/src/api.js`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/BridgePanel.test.jsx` (create)

**Interfaces:**
- Consumes: endpoints from Task 5.
- Produces: exported `BridgeTrackControls` and `BridgePanel` components; `api.bridgeSetTempo/bridgeSetMixerTrack/bridgeSelectTrack/bridgeMuteTrack/bridgeSoloTrack`.

- [ ] **Step 1: Add the API helpers**

In `frontend/src/api.js`, add to the `api` object (after the existing `installBridgeScripts` line):

```javascript
  bridgeSetTempo: (bpm) => request('/api/bridge/tempo', { method: 'POST', body: JSON.stringify({ bpm }) }),
  bridgeSetMixerTrack: (index, body) => request(`/api/bridge/mixer/${index}`, { method: 'POST', body: JSON.stringify(body) }),
  bridgeSelectTrack: (index) => request(`/api/bridge/mixer/${index}/select`, { method: 'POST' }),
  bridgeMuteTrack: (index) => request(`/api/bridge/mixer/${index}/mute`, { method: 'POST' }),
  bridgeSoloTrack: (index) => request(`/api/bridge/mixer/${index}/solo`, { method: 'POST' }),
```

- [ ] **Step 2: Write the failing component test**

Create `frontend/src/BridgePanel.test.jsx`:

```jsx
import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import { BridgePanel, BridgeTrackControls } from './App';

test('track controls fire select/mute/solo with the track index', () => {
  const onSelectTrack = vi.fn();
  const onMuteTrack = vi.fn();
  const onSoloTrack = vi.fn();
  const track = { index: 2, name: 'Bass', volume: 0.7, pan: 0.5, selected: false, slots: [] };
  render(
    <BridgeTrackControls
      track={track}
      busy={false}
      onSetMixerTrack={() => {}}
      onSelectTrack={onSelectTrack}
      onMuteTrack={onMuteTrack}
      onSoloTrack={onSoloTrack}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /^select$/i }));
  fireEvent.click(screen.getByRole('button', { name: /^mute$/i }));
  fireEvent.click(screen.getByRole('button', { name: /^solo$/i }));
  expect(onSelectTrack).toHaveBeenCalledWith(2);
  expect(onMuteTrack).toHaveBeenCalledWith(2);
  expect(onSoloTrack).toHaveBeenCalledWith(2);
});

test('track controls Apply sends only changed name', () => {
  const onSetMixerTrack = vi.fn();
  const track = { index: 1, name: 'Keys', volume: 0.7, pan: 0.5, selected: false, slots: [] };
  render(
    <BridgeTrackControls
      track={track}
      busy={false}
      onSetMixerTrack={onSetMixerTrack}
      onSelectTrack={() => {}}
      onMuteTrack={() => {}}
      onSoloTrack={() => {}}
    />,
  );
  fireEvent.change(screen.getByLabelText(/track 1 name/i), { target: { value: 'Lead Keys' } });
  fireEvent.click(screen.getByRole('button', { name: /^apply$/i }));
  expect(onSetMixerTrack).toHaveBeenCalledWith(1, { name: 'Lead Keys' });
});

test('sync tempo button sends the song bpm', () => {
  const onSetTempo = vi.fn();
  const bridge = {
    status: 'connected', message: 'ok',
    transport: { playing: false, tempo: 120 }, tracks: [], setup: [], errors: [],
  };
  render(
    <BridgePanel
      bridge={bridge}
      setupPlan={{ status: 'ready', checks: [], manualSteps: [] }}
      busy={false}
      songBpm={120}
      onRefresh={() => {}}
      onRefreshSetup={() => {}}
      onInstallScripts={() => {}}
      onTransportAction={() => {}}
      onSetTempo={onSetTempo}
      onSetMixerTrack={() => {}}
      onSelectTrack={() => {}}
      onMuteTrack={() => {}}
      onSoloTrack={() => {}}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /sync tempo/i }));
  expect(onSetTempo).toHaveBeenCalledWith(120);
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd frontend && npm test -- BridgePanel.test.jsx`
Expected: FAIL — `BridgeTrackControls`/`BridgePanel` are not exported.

- [ ] **Step 4: Add `BridgeTrackControls`, export `BridgePanel`, render controls, add sync-tempo**

In `frontend/src/App.jsx`:

(a) Add `useState` is already imported. Add this component immediately before `function BridgePanel(`:

```jsx
export function BridgeTrackControls({ track, busy, onSetMixerTrack, onSelectTrack, onMuteTrack, onSoloTrack }) {
  const [name, setName] = useState(track.name ?? '');
  const [volume, setVolume] = useState(track.volume ?? '');
  const [pan, setPan] = useState(track.pan ?? '');

  function applyEdits() {
    const body = {};
    if (name !== (track.name ?? '')) body.name = name;
    if (volume !== '' && Number(volume) !== track.volume) body.volume = Number(volume);
    if (pan !== '' && Number(pan) !== track.pan) body.pan = Number(pan);
    if (Object.keys(body).length > 0) onSetMixerTrack(track.index, body);
  }

  return (
    <div className="track-controls">
      <input
        aria-label={`Track ${track.index} name`}
        value={name}
        onChange={(event) => setName(event.target.value)}
      />
      <input
        aria-label={`Track ${track.index} volume`}
        type="number" min="0" max="1" step="0.01"
        value={volume}
        onChange={(event) => setVolume(event.target.value)}
      />
      <input
        aria-label={`Track ${track.index} pan`}
        type="number" min="-1" max="1" step="0.01"
        value={pan}
        onChange={(event) => setPan(event.target.value)}
      />
      <button type="button" className="secondary-button compact-button" disabled={busy} onClick={applyEdits}>Apply</button>
      <button type="button" className="secondary-button compact-button" disabled={busy} onClick={() => onSelectTrack(track.index)}>Select</button>
      <button type="button" className="secondary-button compact-button" disabled={busy} onClick={() => onMuteTrack(track.index)}>Mute</button>
      <button type="button" className="secondary-button compact-button" disabled={busy} onClick={() => onSoloTrack(track.index)}>Solo</button>
    </div>
  );
}
```

(b) Change the `BridgePanel` declaration to a named export and accept the new props:

```jsx
export function BridgePanel({ bridge, setupPlan, busy, songBpm, onRefresh, onRefreshSetup, onInstallScripts, onTransportAction, onSetTempo, onSetMixerTrack, onSelectTrack, onMuteTrack, onSoloTrack }) {
```

(c) In the `transport-actions` block, add a sync-tempo button after the Stop button:

```jsx
        <button
          className="secondary-button compact-button"
          disabled={busy || !connected || !songBpm}
          onClick={() => onSetTempo(songBpm)}
        >
          <Gauge size={17} />
          Sync tempo{songBpm ? ` (${songBpm})` : ''}
        </button>
```

(d) Replace the existing read-only track render block:

```jsx
            {(bridge.tracks ?? []).map((track) => (
              <div className={`bridge-track ${track.selected ? 'selected' : ''}`} key={track.index}>
                <span>{track.index}</span>
                <div>
                  <strong>{track.name || `Track ${track.index}`}</strong>
                  <small>
                    Vol {track.volume ?? 'n/a'} · Pan {track.pan ?? 'n/a'}
                  </small>
                  {track.slots.length > 0 && <em>{track.slots.join(', ')}</em>}
                </div>
              </div>
            ))}
```

with:

```jsx
            {(bridge.tracks ?? []).map((track) => (
              <div className={`bridge-track ${track.selected ? 'selected' : ''}`} key={track.index}>
                <span>{track.index}</span>
                <div>
                  <strong>{track.name || `Track ${track.index}`}</strong>
                  {track.slots.length > 0 && <em>{track.slots.join(', ')}</em>}
                  <BridgeTrackControls
                    track={track}
                    busy={busy || !connected}
                    onSetMixerTrack={onSetMixerTrack}
                    onSelectTrack={onSelectTrack}
                    onMuteTrack={onMuteTrack}
                    onSoloTrack={onSoloTrack}
                  />
                </div>
              </div>
            ))}
```

- [ ] **Step 5: Wire handlers at the `BridgePanel` call site in `App`**

In `frontend/src/App.jsx`, replace the existing `<BridgePanel ... />` usage with:

```jsx
        <BridgePanel
          bridge={bridge}
          setupPlan={bridgeSetup}
          busy={busy}
          songBpm={song?.bpm}
          onRefresh={() => runTask(refreshBridge, { adoptCurrent: false })}
          onRefreshSetup={() => runTask(refreshBridgeSetup, { adoptCurrent: false })}
          onInstallScripts={() => runTask(async () => {
            await api.installBridgeScripts();
            await refreshBridgeSetup();
            setMessage('Flapi controller scripts installed. Restart FL Studio, then refresh bridge health.');
          }, { adoptCurrent: false })}
          onTransportAction={(action) => runTask(async () => {
            const next = await api.bridgeTransport(action);
            setBridge(next);
            setMessage(`FL transport ${action} command sent.`);
          }, { adoptCurrent: false })}
          onSetTempo={(bpm) => runTask(async () => {
            const next = await api.bridgeSetTempo(bpm);
            setBridge(next);
            setMessage(`Sent tempo ${bpm} BPM to FL.`);
          }, { adoptCurrent: false })}
          onSetMixerTrack={(index, body) => runTask(async () => {
            const next = await api.bridgeSetMixerTrack(index, body);
            setBridge(next);
            setMessage(`Updated FL mixer track ${index}.`);
          }, { adoptCurrent: false })}
          onSelectTrack={(index) => runTask(async () => {
            const next = await api.bridgeSelectTrack(index);
            setBridge(next);
            setMessage(`Selected FL mixer track ${index}.`);
          }, { adoptCurrent: false })}
          onMuteTrack={(index) => runTask(async () => {
            const next = await api.bridgeMuteTrack(index);
            setBridge(next);
            setMessage(`Toggled mute on FL mixer track ${index}.`);
          }, { adoptCurrent: false })}
          onSoloTrack={(index) => runTask(async () => {
            const next = await api.bridgeSoloTrack(index);
            setBridge(next);
            setMessage(`Toggled solo on FL mixer track ${index}.`);
          }, { adoptCurrent: false })}
        />
```

- [ ] **Step 6: Add styling**

Append to `frontend/src/styles.css`:

```css
.track-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}

.track-controls input {
  width: 64px;
}

.track-controls input[aria-label$="name"] {
  width: 120px;
}
```

- [ ] **Step 7: Run the test + full frontend suite + build**

Run: `cd frontend && npm test -- BridgePanel.test.jsx`
Expected: PASS (3 tests).

Run: `cd frontend && npm test`
Expected: PASS (all existing + the new bridge tests).

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api.js frontend/src/App.jsx frontend/src/styles.css frontend/src/BridgePanel.test.jsx
git commit -m "feat: live mixer write controls in the bridge panel

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Live FL Studio acceptance (manual, user-run)

Not a code task. Requires FL Studio 2025 running with the Flapi controller scripts enabled in MIDI settings.

- [ ] **Step 1: Start backend + frontend**

```powershell
cd 'C:\Users\HP\Vocals APP\fl-connector\backend'
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```
```powershell
cd 'C:\Users\HP\Vocals APP\fl-connector\frontend'
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

- [ ] **Step 2: Connect the bridge**

In FL Studio: Options > MIDI Settings, enable the Flapi Request and Flapi Response controller scripts. In the app's Bridge panel, click Refresh Bridge until it shows `connected` with live tracks.

- [ ] **Step 3: Exercise each write and confirm in FL**

- Generate a song draft, click **Sync tempo** → FL project tempo matches the draft BPM.
- On a track row: change the name and click **Apply** → FL mixer track renamed.
- Change volume/pan and **Apply** → FL fader/pan moves.
- Click **Select** → that mixer track becomes focused in FL.
- Click **Mute**, then **Mute** again → mute toggles in FL. Same for **Solo**.
- Confirm FL's **Ctrl+Z** reverses each change (reversibility).

- [ ] **Step 4: Record results**

If `REC_Tempo` doesn't move the tempo, note the observed behavior so the tempo encoding/flags can be corrected (Decision D2). Record any mismatch between a button and FL's response.

---

## Self-Review

**Spec coverage:**
- run_bridge_write helper → Task 1. Tempo sync → Task 2. Mixer name/vol/pan → Task 3. Select/mute/solo → Task 4 (mute/solo as toggles — documented deviation). Endpoints → Task 5. Frontend per-action controls + sync tempo → Task 6. Live acceptance → Task 7. Read-only-probe invariant preserved (Task 1 keeps the probe write-free; existing invariant test still runs). All spec sections covered.

**Placeholder scan:** No TBD/TODO; every code step has complete code.

**Type consistency:** `run_bridge_write(fl_code, message, client_factory)`, `set_project_tempo(bpm)`, `set_mixer_track(index, *, name, volume, pan)`, `select_mixer_track(index)`, `set_mixer_track_mute(index)`, `set_mixer_track_solo(index)`, endpoint names `bridge_set_tempo/bridge_set_mixer_track/bridge_select_mixer_track/bridge_mute_mixer_track/bridge_solo_mixer_track`, request models `BridgeTempoRequest`/`BridgeMixerTrackRequest`, and frontend `api.bridgeSetTempo/bridgeSetMixerTrack/bridgeSelectTrack/bridgeMuteTrack/bridgeSoloTrack` + props `onSetTempo/onSetMixerTrack/onSelectTrack/onMuteTrack/onSoloTrack` are consistent across tasks and tests.

**Note:** Mute/solo are bodyless toggles (no `{on}`), a deliberate refinement of the spec because the snapshot carries no mute/solo state and FL toggles natively.
