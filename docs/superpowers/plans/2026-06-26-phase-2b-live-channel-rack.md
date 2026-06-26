# Phase 2b — Live Channel Rack Writes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reversible live Channel Rack writes — per channel name / volume / pan plus select / mute / solo toggles — surfaced in the bridge snapshot and editable from the Bridge panel, each behind an explicit per-action Apply.

**Architecture:** Reuse Phase 2a's `run_bridge_write` helper unchanged. The one new element is the read side: extend `READ_ONLY_FL_PROBE` to also collect channels (global indexing) and add a `BridgeChannel` contract + additive `channels`/`channelCount`/`selectedChannel` snapshot fields. Typed channel write functions build one-shot `channels.*` FL scripts; thin FastAPI endpoints expose them; the React Bridge panel gets a "Channel Rack" section mirroring the mixer controls.

**Tech Stack:** Python 3.11 / FastAPI / pytest (backend venv at `backend/.venv`); React 18 / Vite / Vitest / @testing-library/react (frontend).

## Global Constraints

- Working dir: `C:\Users\HP\Vocals APP\fl-connector`. Branch: `phase-2b-live-channel-rack` (already created off master; spec committed at `38dd7ef`).
- Backend test command: `cd backend && ./.venv/Scripts/python -m pytest -q`. Frontend: `cd frontend && npm test`; build `npm run build`.
- The read-only probe `READ_ONLY_FL_PROBE` must stay free of write calls — `test_read_only_probe_does_not_include_write_actions` must keep passing. All channel reads in the probe are pure getters.
- **Global channel indexing everywhere**: reads use `channels.channelCount(True)` and getters with `useGlobalIndex=True`; writes use setters with `useGlobalIndex=True`. This keeps the app and FL agreeing on "channel N" regardless of the Channel Rack group/filter shown in FL.
- FL channel volume scale is 0–1. Pan −1..1. Channel name ≤ 100 chars (≥ 1 after strip). Channel index guard 0–511 (FL enforces real existence).
- New snapshot fields are **additive** (`channels` default `[]`, `channelCount`/`selectedChannel` default `None`) so existing snapshots/tests parse unchanged. Existing 2a `FakeClient` test fixtures are NOT modified — the backend reads channel keys defensively (missing → empty/None).
- Each FL code string interpolates only validated numbers and a `json.dumps`-encoded name (injection-safe).
- Channel/instrument creation and note placement are NOT in scope (the API cannot do them).

**Spec:** `docs/superpowers/specs/2026-06-26-phase-2b-live-channel-rack-design.md`

---

## Task 1: Channel read — probe + `BridgeChannel` contract + snapshot reader

**Files:**
- Modify: `backend/app/contracts.py`
- Modify: `backend/app/bridge.py`
- Test: `backend/tests/test_bridge.py`, `backend/tests/test_contracts.py`

**Interfaces:**
- Produces: `BridgeChannel` dataclass (`index:int, name:str, volume:float|None, pan:float|None, muted:bool, solo:bool, selected:bool`) with `from_dict`/`validate`/`to_dict`; `BridgeSnapshot` gains `channelCount:int|None`, `selectedChannel:int|None`, `channels:list[BridgeChannel]`. `READ_ONLY_FL_PROBE` additionally defines `__fl_connector_bridge_snapshot__["channels"|"channelCount"|"selectedChannel"]`. `_read_bridge_snapshot` reads them defensively.
- Consumes: existing `BridgeMixerTrack` pattern, `_snapshot_key_expression`, `SNAPSHOT_VARIABLE`.

- [ ] **Step 1: Write the failing contract test**

Add to `backend/tests/test_contracts.py`:

```python
def test_bridge_channel_round_trips_and_validates():
    import pytest
    from app.contracts import BridgeChannel, ContractError

    channel = BridgeChannel.from_dict(
        {"index": 1, "name": "Snare", "volume": 0.7, "pan": -0.1,
         "muted": True, "solo": False, "selected": True}
    )
    assert channel.name == "Snare"
    assert channel.muted is True
    assert channel.to_dict()["volume"] == 0.7

    with pytest.raises(ContractError):
        BridgeChannel.from_dict({"index": 0, "name": "x", "volume": 2.0})
    with pytest.raises(ContractError):
        BridgeChannel.from_dict({"index": 0, "name": "x", "pan": 5.0})


def test_bridge_snapshot_round_trips_channels():
    from app.contracts import BridgeSnapshot

    snapshot = BridgeSnapshot.from_dict(
        {
            "status": "connected", "message": "ok", "source": "flapi",
            "flVersion": "v2025", "projectTitle": "P", "selectedTrack": 0, "trackCount": 0,
            "transport": {
                "playing": False, "recording": False, "loopMode": 0,
                "songPosition": 0.0, "songPositionHint": "", "songLengthBars": None, "tempo": 120.0,
            },
            "tracks": [], "setup": [], "errors": [],
            "channelCount": 2, "selectedChannel": 1,
            "channels": [
                {"index": 0, "name": "Kick", "volume": 0.8, "pan": 0.0, "muted": False, "solo": False, "selected": False},
                {"index": 1, "name": "Snare", "volume": 0.7, "pan": -0.1, "muted": True, "solo": False, "selected": True},
            ],
        }
    )
    assert snapshot.channelCount == 2
    assert snapshot.selectedChannel == 1
    assert [c.name for c in snapshot.channels] == ["Kick", "Snare"]
    assert snapshot.to_dict()["channels"][1]["muted"] is True


def test_bridge_snapshot_defaults_channels_to_empty():
    from app.contracts import BridgeSnapshot

    snapshot = BridgeSnapshot.from_dict(
        {
            "status": "disconnected", "message": "no fl", "source": "flapi",
            "transport": None, "tracks": [], "setup": [], "errors": [],
        }
    )
    assert snapshot.channels == []
    assert snapshot.channelCount is None
    assert snapshot.selectedChannel is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_contracts.py::test_bridge_channel_round_trips_and_validates -q`
Expected: FAIL — `ImportError: cannot import name 'BridgeChannel'`.

- [ ] **Step 3: Add the `BridgeChannel` contract and extend `BridgeSnapshot`**

In `backend/app/contracts.py`, ensure the dataclasses import includes `field`:

```python
from dataclasses import dataclass, field
```

Add this dataclass immediately before `class BridgeSnapshot:`:

```python
@dataclass(frozen=True)
class BridgeChannel:
    index: int
    name: str
    volume: float | None
    pan: float | None
    muted: bool
    solo: bool
    selected: bool

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BridgeChannel":
        volume = value.get("volume")
        pan = value.get("pan")
        channel = cls(
            index=int(value["index"]),
            name=str(value.get("name", "")),
            volume=float(volume) if volume is not None else None,
            pan=float(pan) if pan is not None else None,
            muted=bool(value.get("muted", False)),
            solo=bool(value.get("solo", False)),
            selected=bool(value.get("selected", False)),
        )
        channel.validate()
        return channel

    def validate(self) -> None:
        if self.index < 0:
            raise ContractError("bridge channel index must be >= 0")
        if self.volume is not None and not 0 <= self.volume <= 1:
            raise ContractError("bridge channel volume must be 0-1")
        if self.pan is not None and not -1 <= self.pan <= 1:
            raise ContractError("bridge channel pan must be -1 to 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "volume": round(self.volume, 4) if self.volume is not None else None,
            "pan": round(self.pan, 4) if self.pan is not None else None,
            "muted": self.muted,
            "solo": self.solo,
            "selected": self.selected,
        }
```

In `class BridgeSnapshot:`, add three fields at the END of the field list (after `errors`), so the defaulted fields follow the non-default ones:

```python
    channelCount: int | None = None
    selectedChannel: int | None = None
    channels: list[BridgeChannel] = field(default_factory=list)
```

In `BridgeSnapshot.from_dict`, read the new values (add near the top of the method, beside `selected_track`):

```python
        channel_count = value.get("channelCount")
        selected_channel = value.get("selectedChannel")
```

and pass them in the `cls(...)` call (after the `errors=` line):

```python
            channelCount=int(channel_count) if channel_count is not None else None,
            selectedChannel=int(selected_channel) if selected_channel is not None else None,
            channels=[BridgeChannel.from_dict(channel) for channel in value.get("channels", [])],
```

In `BridgeSnapshot.validate`, add after the `trackCount` check:

```python
        if self.channelCount is not None and self.channelCount < 0:
            raise ContractError("bridge channelCount must be >= 0")
        if self.selectedChannel is not None and self.selectedChannel < 0:
            raise ContractError("bridge selectedChannel must be >= 0")
        for channel in self.channels:
            channel.validate()
```

In `BridgeSnapshot.to_dict`, add after the `"tracks"` entry:

```python
            "channelCount": self.channelCount,
            "selectedChannel": self.selectedChannel,
            "channels": [channel.to_dict() for channel in self.channels],
```

- [ ] **Step 4: Run the contract tests**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_contracts.py -q`
Expected: PASS (new tests + existing contract tests).

- [ ] **Step 5: Write the failing probe-read test**

Add to `backend/tests/test_bridge.py`:

```python
def test_probe_reads_channels_into_snapshot():
    from app.bridge import probe_bridge

    class FakeClient:
        def exec(self, code):
            self.last_code = code

        def eval(self, expression):
            values = {
                '__fl_connector_bridge_snapshot__["flVersion"]': "Producer Edition v2025",
                '__fl_connector_bridge_snapshot__["projectTitle"]': "Channel project",
                '__fl_connector_bridge_snapshot__["selectedTrack"]': 0,
                '__fl_connector_bridge_snapshot__["trackCount"]': 0,
                '__fl_connector_bridge_snapshot__["transport"]': {
                    "playing": False, "recording": False, "loopMode": 0,
                    "songPosition": 0.0, "songPositionHint": "", "songLengthBars": None, "tempo": 120.0,
                },
                '__fl_connector_bridge_snapshot__["channelCount"]': 2,
                '__fl_connector_bridge_snapshot__["selectedChannel"]': 1,
                'len(__fl_connector_bridge_snapshot__["tracks"])': 0,
                'len(__fl_connector_bridge_snapshot__["channels"])': 2,
                '__fl_connector_bridge_snapshot__["channels"][0]': {
                    "index": 0, "name": "Kick", "volume": 0.8, "pan": 0.0,
                    "muted": False, "solo": False, "selected": False,
                },
                '__fl_connector_bridge_snapshot__["channels"][1]': {
                    "index": 1, "name": "Snare", "volume": 0.7, "pan": -0.1,
                    "muted": True, "solo": False, "selected": True,
                },
                '__fl_connector_bridge_snapshot__["errors"]': [],
            }
            return values[expression]

        def close(self):
            pass

    snapshot = probe_bridge(client_factory=FakeClient)

    assert snapshot.status == "connected"
    assert snapshot.channelCount == 2
    assert snapshot.selectedChannel == 1
    assert [c.name for c in snapshot.channels] == ["Kick", "Snare"]
    assert snapshot.channels[1].muted is True
    assert snapshot.channels[1].selected is True


def test_read_only_probe_includes_channel_getters_not_setters():
    from app.bridge import READ_ONLY_FL_PROBE

    assert "import channels" in READ_ONLY_FL_PROBE
    assert "channels.getChannelName" in READ_ONLY_FL_PROBE
    assert "channels.channelCount" in READ_ONLY_FL_PROBE
```

- [ ] **Step 6: Run to verify it fails**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_bridge.py::test_probe_reads_channels_into_snapshot -q`
Expected: FAIL — `KeyError` on `'__fl_connector_bridge_snapshot__["channelCount"]'` (the reader does not yet request channel keys) or the channels assertion fails (empty list).

- [ ] **Step 7: Extend the probe and the snapshot reader**

In `backend/app/bridge.py`, in the `READ_ONLY_FL_PROBE` string, add `import channels` to the import block at the top of the probe (after `import mixer`):

```python
import mixer
import channels
import plugins
```

In the same probe string, immediately AFTER the `for track_index in range(...)` loop that builds `tracks` and BEFORE the `__fl_connector_bridge_snapshot__ = {` assignment, add the channel-collection block:

```python
channel_count = _safe("channels.channelCount", lambda: channels.channelCount(True), 0) or 0
selected_channel = _safe("channels.selectedChannel", lambda: channels.selectedChannel(True, 0, True), None)
channels_list = []
for channel_index in range(min(int(channel_count), 32)):
    channels_list.append({
        "index": channel_index,
        "name": _safe("channels.getChannelName(" + str(channel_index) + ")", lambda: channels.getChannelName(channel_index, True), ""),
        "volume": _safe("channels.getChannelVolume(" + str(channel_index) + ")", lambda: channels.getChannelVolume(channel_index, False, True), None),
        "pan": _safe("channels.getChannelPan(" + str(channel_index) + ")", lambda: channels.getChannelPan(channel_index, True), None),
        "muted": bool(_safe("channels.isChannelMuted(" + str(channel_index) + ")", lambda: channels.isChannelMuted(channel_index, True), False)),
        "solo": bool(_safe("channels.isChannelSolo(" + str(channel_index) + ")", lambda: channels.isChannelSolo(channel_index, True), False)),
        "selected": bool(_safe("channels.isChannelSelected(" + str(channel_index) + ")", lambda: channels.isChannelSelected(channel_index, True), False)),
    })
```

In the `__fl_connector_bridge_snapshot__ = { ... }` dict in the probe, add these three keys (after the `"tracks": tracks,` line):

```python
    "channelCount": channel_count,
    "selectedChannel": selected_channel,
    "channels": channels_list,
```

Now add a defensive eval helper and extend `_read_bridge_snapshot`. Add this helper above `_read_bridge_snapshot`:

```python
def _eval_optional(client: Any, expression: str, fallback: Any = None) -> Any:
    try:
        return client.eval(expression)
    except Exception:
        return fallback
```

In `_read_bridge_snapshot`, after the block that builds `snapshot["tracks"]` and before `snapshot["errors"] = ...`, add:

```python
    snapshot["channelCount"] = _eval_optional(client, _snapshot_key_expression("channelCount"))
    snapshot["selectedChannel"] = _eval_optional(client, _snapshot_key_expression("selectedChannel"))
    channel_count = int(_eval_optional(client, f'len({SNAPSHOT_VARIABLE}["channels"])', 0) or 0)
    snapshot["channels"] = [
        client.eval(f'{SNAPSHOT_VARIABLE}["channels"][{channel_index}]')
        for channel_index in range(channel_count)
    ]
```

(The defensive reads keep every existing 2a `FakeClient` — which does not supply channel keys — working: missing keys → `None`/`0` → `channels` defaults to `[]`.)

- [ ] **Step 8: Extend the read-only invariant test with channel write bans**

In `backend/tests/test_bridge.py`, in `test_read_only_probe_does_not_include_write_actions`, add these entries to `banned_calls` (chosen so they do NOT collide with the getters `channels.selectedChannel` / `channels.isChannelSelected`):

```python
        "channels.setChannel",
        "channels.muteChannel",
        "channels.soloChannel",
        "channels.selectOneChannel",
```

- [ ] **Step 9: Run the bridge tests + full suite**

Run: `cd backend && ./.venv/Scripts/python -m pytest -q`
Expected: PASS — new channel read tests, the invariant test, and all existing tests (the defensive read leaves 2a fixtures untouched).

- [ ] **Step 10: Commit**

```bash
git add backend/app/contracts.py backend/app/bridge.py backend/tests/test_bridge.py backend/tests/test_contracts.py
git commit -m "feat: surface FL Channel Rack in the read-only bridge snapshot

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `set_channel` (name / volume / pan)

**Files:**
- Modify: `backend/app/bridge.py`
- Test: `backend/tests/test_bridge.py`

**Interfaces:**
- Produces: `_require_channel_index(index:int) -> None` (raises `ValueError` if not 0–511); `set_channel(index:int, *, name:str|None=None, volume:float|None=None, pan:float|None=None, client_factory=None) -> BridgeSnapshot`. Raises `ValueError` if index out of range, no field given, name empty/>100, volume not 0–1, or pan not −1..1.
- Consumes: `run_bridge_write` (Phase 2a), `json` (already imported in bridge.py).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_bridge.py`:

```python
def test_set_channel_builds_code_for_provided_fields():
    from app.bridge import set_channel

    captured = {}

    class FakeClient:
        def exec(self, code):
            captured.setdefault("code", code)

        def eval(self, expression):
            values = {
                '__fl_connector_bridge_snapshot__["flVersion"]': "v2025",
                '__fl_connector_bridge_snapshot__["projectTitle"]': "Chan",
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

    snapshot = set_channel(2, name='Lead "Bass"', volume=0.72, pan=-0.25, client_factory=FakeClient)
    assert snapshot.status == "connected"
    assert captured["code"] == (
        "import channels\n"
        'channels.setChannelName(2, "Lead \\"Bass\\"", useGlobalIndex=True)\n'
        "channels.setChannelVolume(2, 0.72, useGlobalIndex=True)\n"
        "channels.setChannelPan(2, -0.25, useGlobalIndex=True)"
    )


def test_set_channel_validates_inputs():
    import pytest
    from app.bridge import set_channel

    with pytest.raises(ValueError):
        set_channel(2)  # no fields
    with pytest.raises(ValueError):
        set_channel(600, name="x")  # index
    with pytest.raises(ValueError):
        set_channel(2, name="")  # empty name
    with pytest.raises(ValueError):
        set_channel(2, name="   ")  # whitespace-only name
    with pytest.raises(ValueError):
        set_channel(2, name="x" * 101)  # too-long name
    with pytest.raises(ValueError):
        set_channel(2, volume=2.0)  # volume
    with pytest.raises(ValueError):
        set_channel(2, pan=5.0)  # pan
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_bridge.py::test_set_channel_builds_code_for_provided_fields -q`
Expected: FAIL — `ImportError: cannot import name 'set_channel'`.

- [ ] **Step 3: Implement**

In `backend/app/bridge.py`, add after the mixer write functions (e.g., after `set_mixer_track`):

```python
def _require_channel_index(index: int) -> None:
    if not 0 <= index <= 511:
        raise ValueError("channel index must be between 0 and 511")


def set_channel(
    index: int,
    *,
    name: str | None = None,
    volume: float | None = None,
    pan: float | None = None,
    client_factory: Callable[[], Any] | None = None,
) -> BridgeSnapshot:
    _require_channel_index(index)
    if name is None and volume is None and pan is None:
        raise ValueError("provide at least one of name, volume, or pan")
    lines = ["import channels"]
    changed: list[str] = []
    if name is not None:
        if not name.strip() or len(name) > 100:
            raise ValueError("channel name must be 1-100 characters")
        lines.append(f"channels.setChannelName({index}, {json.dumps(name)}, useGlobalIndex=True)")
        changed.append("name")
    if volume is not None:
        if not 0 <= volume <= 1:
            raise ValueError("volume must be between 0 and 1")
        lines.append(f"channels.setChannelVolume({index}, {round(volume, 4)}, useGlobalIndex=True)")
        changed.append("volume")
    if pan is not None:
        if not -1 <= pan <= 1:
            raise ValueError("pan must be between -1 and 1")
        lines.append(f"channels.setChannelPan({index}, {round(pan, 4)}, useGlobalIndex=True)")
        changed.append("pan")
    message = f"Updated FL channel {index} ({', '.join(changed)})."
    return run_bridge_write("\n".join(lines), message, client_factory=client_factory)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_bridge.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/bridge.py backend/tests/test_bridge.py
git commit -m "feat: add live FL channel name/volume/pan write

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `select_channel`, `set_channel_mute`, `set_channel_solo`

**Files:**
- Modify: `backend/app/bridge.py`
- Test: `backend/tests/test_bridge.py`

**Interfaces:**
- Produces: `select_channel(index, client_factory=None)`, `set_channel_mute(index, client_factory=None)`, `set_channel_solo(index, client_factory=None)` — each `-> BridgeSnapshot`, each raises `ValueError` if index not 0–511. Mute/solo TOGGLE.
- Consumes: `_require_channel_index` (Task 2), `run_bridge_write` (Phase 2a).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_bridge.py`:

```python
def test_channel_select_mute_solo_emit_expected_code():
    import pytest
    from app.bridge import select_channel, set_channel_mute, set_channel_solo

    def fake_factory(expected_first):
        class FakeClient:
            def exec(self, code):
                if not hasattr(self, "first"):
                    self.first = code
                    assert code == expected_first

            def eval(self, expression):
                values = {
                    '__fl_connector_bridge_snapshot__["flVersion"]': "v2025",
                    '__fl_connector_bridge_snapshot__["projectTitle"]': "C",
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

    assert select_channel(2, client_factory=fake_factory("import channels\nchannels.selectOneChannel(2, useGlobalIndex=True)")).status == "connected"
    assert set_channel_mute(2, client_factory=fake_factory("import channels\nchannels.muteChannel(2, useGlobalIndex=True)")).status == "connected"
    assert set_channel_solo(2, client_factory=fake_factory("import channels\nchannels.soloChannel(2, useGlobalIndex=True)")).status == "connected"

    with pytest.raises(ValueError):
        select_channel(600, client_factory=fake_factory(""))
    with pytest.raises(ValueError):
        set_channel_mute(-1, client_factory=fake_factory(""))
    with pytest.raises(ValueError):
        set_channel_solo(600, client_factory=fake_factory(""))
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_bridge.py::test_channel_select_mute_solo_emit_expected_code -q`
Expected: FAIL — `ImportError: cannot import name 'select_channel'`.

- [ ] **Step 3: Implement**

In `backend/app/bridge.py`, add after `set_channel`:

```python
def select_channel(
    index: int, client_factory: Callable[[], Any] | None = None
) -> BridgeSnapshot:
    _require_channel_index(index)
    return run_bridge_write(
        f"import channels\nchannels.selectOneChannel({index}, useGlobalIndex=True)",
        f"Selected FL channel {index}.",
        client_factory=client_factory,
    )


def set_channel_mute(
    index: int, client_factory: Callable[[], Any] | None = None
) -> BridgeSnapshot:
    _require_channel_index(index)
    return run_bridge_write(
        f"import channels\nchannels.muteChannel({index}, useGlobalIndex=True)",
        f"Toggled mute on FL channel {index}.",
        client_factory=client_factory,
    )


def set_channel_solo(
    index: int, client_factory: Callable[[], Any] | None = None
) -> BridgeSnapshot:
    _require_channel_index(index)
    return run_bridge_write(
        f"import channels\nchannels.soloChannel({index}, useGlobalIndex=True)",
        f"Toggled solo on FL channel {index}.",
        client_factory=client_factory,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_bridge.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/bridge.py backend/tests/test_bridge.py
git commit -m "feat: add live FL channel select/mute/solo toggles

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Channel write endpoints

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_bridge.py`

**Interfaces:**
- Consumes: `set_channel`, `select_channel`, `set_channel_mute`, `set_channel_solo` (Tasks 2–3).
- Produces: routes `POST /api/bridge/channel/{index}`, `POST /api/bridge/channel/{index}/select`, `POST /api/bridge/channel/{index}/mute`, `POST /api/bridge/channel/{index}/solo`, each returning a `BridgeSnapshot` dict; request model `BridgeChannelRequest`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_bridge.py`:

```python
def test_bridge_channel_endpoints_route_to_functions(monkeypatch):
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
                "channelCount": 0, "selectedChannel": None, "channels": [],
            }
        )

    calls = []
    monkeypatch.setattr(main_module, "set_channel", lambda index, name=None, volume=None, pan=None: calls.append(("set", index, name, volume, pan)) or fake_snapshot("c"))
    monkeypatch.setattr(main_module, "select_channel", lambda index: calls.append(("select", index)) or fake_snapshot("s"))
    monkeypatch.setattr(main_module, "set_channel_mute", lambda index: calls.append(("mute", index)) or fake_snapshot("mu"))
    monkeypatch.setattr(main_module, "set_channel_solo", lambda index: calls.append(("solo", index)) or fake_snapshot("so"))

    assert main_module.bridge_set_channel(2, main_module.BridgeChannelRequest(name="Bass", volume=0.7, pan=0.0))["status"] == "connected"
    assert main_module.bridge_select_channel(2)["status"] == "connected"
    assert main_module.bridge_mute_channel(2)["status"] == "connected"
    assert main_module.bridge_solo_channel(2)["status"] == "connected"

    assert calls == [
        ("set", 2, "Bass", 0.7, 0.0),
        ("select", 2),
        ("mute", 2),
        ("solo", 2),
    ]


def test_bridge_set_channel_maps_value_error_to_400(monkeypatch):
    import pytest
    from fastapi import HTTPException

    def boom(index, name=None, volume=None, pan=None):
        raise ValueError("channel index must be between 0 and 511")

    monkeypatch.setattr(main_module, "set_channel", boom)
    with pytest.raises(HTTPException) as exc:
        main_module.bridge_set_channel(2, main_module.BridgeChannelRequest(name="x"))
    assert exc.value.status_code == 400
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_bridge.py::test_bridge_channel_endpoints_route_to_functions -q`
Expected: FAIL — `AttributeError: module 'app.main' has no attribute 'bridge_set_channel'`.

- [ ] **Step 3: Implement**

In `backend/app/main.py`, extend the bridge import to add the four channel functions:

```python
from .bridge import (
    probe_bridge,
    run_transport_action,
    select_channel,
    select_mixer_track,
    set_channel,
    set_channel_mute,
    set_channel_solo,
    set_mixer_track,
    set_mixer_track_mute,
    set_mixer_track_solo,
    set_project_tempo,
)
```

Add the request model next to `BridgeMixerTrackRequest`:

```python
class BridgeChannelRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    volume: float | None = Field(default=None, ge=0, le=1)
    pan: float | None = Field(default=None, ge=-1, le=1)
```

Add endpoints immediately after the existing mixer endpoints (e.g., after `bridge_solo_mixer_track`):

```python
@app.post("/api/bridge/channel/{index}")
def bridge_set_channel(index: int, request: BridgeChannelRequest) -> dict[str, Any]:
    try:
        return set_channel(
            index, name=request.name, volume=request.volume, pan=request.pan
        ).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/bridge/channel/{index}/select")
def bridge_select_channel(index: int) -> dict[str, Any]:
    try:
        return select_channel(index).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/bridge/channel/{index}/mute")
def bridge_mute_channel(index: int) -> dict[str, Any]:
    try:
        return set_channel_mute(index).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/bridge/channel/{index}/solo")
def bridge_solo_channel(index: int) -> dict[str, Any]:
    try:
        return set_channel_solo(index).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- [ ] **Step 4: Run to verify it passes + full suite**

Run: `cd backend && ./.venv/Scripts/python -m pytest -q`
Expected: PASS (all existing + the new channel endpoint tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_bridge.py
git commit -m "feat: expose live bridge channel write endpoints

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Frontend Channel Rack controls

**Files:**
- Modify: `frontend/src/api.js`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/ChannelRack.test.jsx` (create)

**Interfaces:**
- Consumes: endpoints from Task 4.
- Produces: exported `BridgeChannelControls` component; `api.bridgeSetChannel/bridgeSelectChannel/bridgeMuteChannel/bridgeSoloChannel`; `BridgePanel` gains props `onSetChannel/onSelectChannel/onMuteChannel/onSoloChannel` and renders a Channel Rack section from `bridge.channels`.

- [ ] **Step 1: Add the API helpers**

In `frontend/src/api.js`, add to the `api` object (after the `bridgeSoloTrack` line):

```javascript
  bridgeSetChannel: (index, body) => request(`/api/bridge/channel/${index}`, { method: 'POST', body: JSON.stringify(body) }),
  bridgeSelectChannel: (index) => request(`/api/bridge/channel/${index}/select`, { method: 'POST' }),
  bridgeMuteChannel: (index) => request(`/api/bridge/channel/${index}/mute`, { method: 'POST' }),
  bridgeSoloChannel: (index) => request(`/api/bridge/channel/${index}/solo`, { method: 'POST' }),
```

- [ ] **Step 2: Write the failing component test**

Create `frontend/src/ChannelRack.test.jsx`:

```jsx
import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import { BridgeChannelControls, BridgePanel } from './App';

test('channel controls fire select/mute/solo with the channel index', () => {
  const onSelectChannel = vi.fn();
  const onMuteChannel = vi.fn();
  const onSoloChannel = vi.fn();
  const channel = { index: 2, name: 'Snare', volume: 0.7, pan: -0.1, muted: false, solo: false, selected: false };
  render(
    <BridgeChannelControls
      channel={channel}
      busy={false}
      onSetChannel={() => {}}
      onSelectChannel={onSelectChannel}
      onMuteChannel={onMuteChannel}
      onSoloChannel={onSoloChannel}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /^select$/i }));
  fireEvent.click(screen.getByRole('button', { name: /^mute$/i }));
  fireEvent.click(screen.getByRole('button', { name: /^solo$/i }));
  expect(onSelectChannel).toHaveBeenCalledWith(2);
  expect(onMuteChannel).toHaveBeenCalledWith(2);
  expect(onSoloChannel).toHaveBeenCalledWith(2);
});

test('channel Apply sends only the changed name', () => {
  const onSetChannel = vi.fn();
  const channel = { index: 1, name: 'Kick', volume: 0.8, pan: 0.0, muted: false, solo: false, selected: false };
  render(
    <BridgeChannelControls
      channel={channel}
      busy={false}
      onSetChannel={onSetChannel}
      onSelectChannel={() => {}}
      onMuteChannel={() => {}}
      onSoloChannel={() => {}}
    />,
  );
  fireEvent.change(screen.getByLabelText(/channel 1 name/i), { target: { value: '808 Kick' } });
  fireEvent.click(screen.getByRole('button', { name: /^apply$/i }));
  expect(onSetChannel).toHaveBeenCalledWith(1, { name: '808 Kick' });
});

test('bridge panel renders a channel rack row from snapshot channels', () => {
  const bridge = {
    status: 'connected', message: 'ok',
    transport: { playing: false, tempo: 120 },
    tracks: [],
    channels: [{ index: 0, name: 'Kick', volume: 0.8, pan: 0.0, muted: false, solo: false, selected: false }],
    setup: [], errors: [],
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
      onSetTempo={() => {}}
      onSetMixerTrack={() => {}}
      onSelectTrack={() => {}}
      onMuteTrack={() => {}}
      onSoloTrack={() => {}}
      onSetChannel={() => {}}
      onSelectChannel={() => {}}
      onMuteChannel={() => {}}
      onSoloChannel={() => {}}
    />,
  );
  expect(screen.getByLabelText(/channel 0 name/i)).toBeInTheDocument();
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd frontend && npm test -- ChannelRack.test.jsx`
Expected: FAIL — `BridgeChannelControls` is not exported.

- [ ] **Step 4: Add `BridgeChannelControls` and render the Channel Rack section**

In `frontend/src/App.jsx`, add this component immediately before `export function BridgePanel(`:

```jsx
export function BridgeChannelControls({ channel, busy, onSetChannel, onSelectChannel, onMuteChannel, onSoloChannel }) {
  const [name, setName] = useState(channel.name ?? '');
  const [volume, setVolume] = useState(channel.volume ?? '');
  const [pan, setPan] = useState(channel.pan ?? '');

  useEffect(() => {
    setName(channel.name ?? '');
    setVolume(channel.volume ?? '');
    setPan(channel.pan ?? '');
  }, [channel.index]);

  function applyEdits() {
    const body = {};
    if (name !== (channel.name ?? '')) body.name = name;
    if (volume !== '' && Number(volume) !== channel.volume) body.volume = Number(volume);
    if (pan !== '' && Number(pan) !== channel.pan) body.pan = Number(pan);
    if (Object.keys(body).length > 0) onSetChannel(channel.index, body);
  }

  return (
    <div className="track-controls">
      <input
        aria-label={`Channel ${channel.index} name`}
        value={name}
        onChange={(event) => setName(event.target.value)}
      />
      <input
        aria-label={`Channel ${channel.index} volume`}
        type="number" min="0" max="1" step="0.01"
        value={volume}
        onChange={(event) => setVolume(event.target.value)}
      />
      <input
        aria-label={`Channel ${channel.index} pan`}
        type="number" min="-1" max="1" step="0.01"
        value={pan}
        onChange={(event) => setPan(event.target.value)}
      />
      <button type="button" className="secondary-button compact-button" disabled={busy} onClick={applyEdits}>Apply</button>
      <button type="button" className="secondary-button compact-button" disabled={busy} onClick={() => onSelectChannel(channel.index)}>Select</button>
      <button type="button" className={`secondary-button compact-button ${channel.muted ? 'active' : ''}`} disabled={busy} onClick={() => onMuteChannel(channel.index)}>Mute</button>
      <button type="button" className={`secondary-button compact-button ${channel.solo ? 'active' : ''}`} disabled={busy} onClick={() => onSoloChannel(channel.index)}>Solo</button>
    </div>
  );
}
```

Change the `BridgePanel` declaration to accept the new props (add them to the destructured props list):

```jsx
export function BridgePanel({ bridge, setupPlan, busy, songBpm, onRefresh, onRefreshSetup, onInstallScripts, onTransportAction, onSetTempo, onSetMixerTrack, onSelectTrack, onMuteTrack, onSoloTrack, onSetChannel, onSelectChannel, onMuteChannel, onSoloChannel }) {
```

Inside `BridgePanel`, immediately AFTER the closing `</div>` (or fragment) of the existing mixer `tracks` block, add the Channel Rack section:

```jsx
        {(bridge.channels ?? []).length > 0 && (
          <div className="bridge-channels">
            <h4>Channel Rack</h4>
            {(bridge.channels ?? []).map((channel) => (
              <div className={`bridge-channel ${channel.selected ? 'selected' : ''}`} key={channel.index}>
                <span>{channel.index}</span>
                <div>
                  <strong>{channel.name || `Channel ${channel.index}`}</strong>
                  <BridgeChannelControls
                    channel={channel}
                    busy={busy || !connected}
                    onSetChannel={onSetChannel}
                    onSelectChannel={onSelectChannel}
                    onMuteChannel={onMuteChannel}
                    onSoloChannel={onSoloChannel}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
```

(Use the same `connected` boolean the panel already computes for the mixer controls. If `useEffect` is not yet imported in `App.jsx`, add it to the existing React import: `import { useEffect, useState } from 'react';`.)

- [ ] **Step 5: Wire handlers at the `BridgePanel` call site in `App`**

In `frontend/src/App.jsx`, add these props to the existing `<BridgePanel ... />` usage (alongside the `onSoloTrack` prop):

```jsx
          onSetChannel={(index, body) => runTask(async () => {
            const next = await api.bridgeSetChannel(index, body);
            setBridge(next);
            setMessage(`Updated FL channel ${index}.`);
          }, { adoptCurrent: false })}
          onSelectChannel={(index) => runTask(async () => {
            const next = await api.bridgeSelectChannel(index);
            setBridge(next);
            setMessage(`Selected FL channel ${index}.`);
          }, { adoptCurrent: false })}
          onMuteChannel={(index) => runTask(async () => {
            const next = await api.bridgeMuteChannel(index);
            setBridge(next);
            setMessage(`Toggled mute on FL channel ${index}.`);
          }, { adoptCurrent: false })}
          onSoloChannel={(index) => runTask(async () => {
            const next = await api.bridgeSoloChannel(index);
            setBridge(next);
            setMessage(`Toggled solo on FL channel ${index}.`);
          }, { adoptCurrent: false })}
```

- [ ] **Step 6: Add styling**

Append to `frontend/src/styles.css`:

```css
.bridge-channels {
  margin-top: 12px;
}

.bridge-channel {
  display: flex;
  gap: 8px;
  padding: 6px 0;
  border-top: 1px solid var(--border, #2a2a2a);
}

.bridge-channel.selected strong {
  color: var(--accent, #6ea8fe);
}

.compact-button.active {
  background: var(--accent, #6ea8fe);
  color: #0b0b0b;
}
```

- [ ] **Step 7: Run the test + full frontend suite + build**

Run: `cd frontend && npm test -- ChannelRack.test.jsx`
Expected: PASS (3 tests).

Run: `cd frontend && npm test`
Expected: PASS (all existing + the new channel tests).

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api.js frontend/src/App.jsx frontend/src/styles.css frontend/src/ChannelRack.test.jsx
git commit -m "feat: live channel rack controls in the bridge panel

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Live FL Studio acceptance (manual, user-run)

Not a code task. Requires FL Studio 2025 running with the Flapi controller scripts enabled in MIDI settings, and a project that has channels in the Channel Rack.

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

In FL Studio: Options > MIDI Settings, enable the Flapi Request and Flapi Response controller scripts. In the app's Bridge panel, click Refresh Bridge until it shows `connected` with a populated Channel Rack section.

- [ ] **Step 3: Exercise each write and confirm in FL's Channel Rack**

- On a channel row: change the name and click **Apply** → that Channel Rack channel is renamed in FL.
- Change volume/pan and **Apply** → the channel's volume/pan knob moves in FL.
- Click **Select** → that channel becomes the focused/selected channel in FL.
- Click **Mute**, then **Mute** again → the channel's mute LED toggles in FL (and the app's Mute button reflects state after refresh). Same for **Solo**.
- Confirm FL's **Ctrl+Z** reverses each name/volume/pan change.

- [ ] **Step 4: Record results**

Confirm the global index shown in the app maps to the same channel in FL (D2), and that volume/pan scale matches the displayed value. Record any mismatch between a button and FL's response so the encoding can be corrected.

---

## Self-Review

**Spec coverage:**
- Read probe + `channels`/`channelCount`/`selectedChannel` snapshot (global indexing) → Task 1. `BridgeChannel` contract → Task 1. `set_channel` name/vol/pan → Task 2. select/mute/solo (toggles) → Task 3. Endpoints + `BridgeChannelRequest` → Task 4. Frontend Channel Rack section + Mute/Solo state reflection → Task 5. Live acceptance → Task 6. Read-only-probe invariant preserved and extended with channel-write bans (Task 1). All spec sections covered. The cut "→ Insert N" routing display is a documented non-goal and intentionally absent.

**Placeholder scan:** No TBD/TODO; every code step contains complete code.

**Type consistency:** `BridgeChannel(index, name, volume, pan, muted, solo, selected)` and snapshot fields `channelCount/selectedChannel/channels` are used identically across contract, reader, endpoint test, and frontend. Backend functions `set_channel(index, *, name, volume, pan)`, `select_channel(index)`, `set_channel_mute(index)`, `set_channel_solo(index)`; endpoint names `bridge_set_channel/bridge_select_channel/bridge_mute_channel/bridge_solo_channel`; request model `BridgeChannelRequest`; frontend `api.bridgeSetChannel/bridgeSelectChannel/bridgeMuteChannel/bridgeSoloChannel` and props `onSetChannel/onSelectChannel/onMuteChannel/onSoloChannel` are consistent across tasks and tests. All channel FL calls use `useGlobalIndex=True`.

**Note:** Mute/solo are bodyless toggles (`muteChannel`/`soloChannel`), but unlike Phase 2a the snapshot carries real mute/solo state (`isChannelMuted`/`isChannelSolo`), so the UI lights the Mute/Solo buttons via the `active` class.
