import pytest
import sys
from types import SimpleNamespace

from app import bridge as bridge_module
from app import main as main_module
from app.bridge import READ_ONLY_FL_PROBE, default_client_factory, probe_bridge, run_transport_action
from app.contracts import BridgeSnapshot, ContractError


def test_bridge_snapshot_round_trips_connected_state():
    snapshot = BridgeSnapshot.from_dict(
        {
            "status": "connected",
            "message": "Live FL bridge responded.",
            "source": "flapi",
            "flVersion": "Producer Edition v2025",
            "projectTitle": "Demo project",
            "selectedTrack": 1,
            "trackCount": 3,
            "transport": {
                "playing": False,
                "recording": False,
                "loopMode": 1,
                "songPosition": 0.0,
                "songPositionHint": "1:01:000",
                "songLengthBars": 8,
                "tempo": 113.0,
            },
            "tracks": [
                {
                    "index": 0,
                    "name": "Master",
                    "volume": 0.8,
                    "pan": 0.5,
                    "selected": False,
                    "slots": ["Fruity Limiter"],
                },
                {
                    "index": 1,
                    "name": "Log drum",
                    "volume": 0.72,
                    "pan": 0.5,
                    "selected": True,
                    "slots": [],
                },
            ],
            "setup": [],
            "errors": [],
        }
    )

    result = snapshot.to_dict()

    assert result["status"] == "connected"
    assert result["transport"]["tempo"] == 113.0
    assert result["tracks"][1]["name"] == "Log drum"
    assert result["tracks"][1]["selected"] is True


def test_bridge_snapshot_rejects_invalid_status():
    with pytest.raises(ContractError):
        BridgeSnapshot.from_dict(
            {
                "status": "running",
                "message": "Bad state",
                "source": "flapi",
                "transport": None,
                "tracks": [],
                "setup": [],
                "errors": [],
            }
        )


def test_bridge_probe_reports_setup_steps_when_flapi_is_missing():
    def missing_client():
        raise ModuleNotFoundError("No module named 'flapi'")

    snapshot = probe_bridge(client_factory=missing_client)

    assert snapshot.status == "disconnected"
    assert "Flapi Python package is not importable" in snapshot.message
    assert any("loopMIDI" in step for step in snapshot.setup)
    assert snapshot.tracks == []


def test_default_client_factory_uses_top_level_flapi_api(monkeypatch):
    calls = []
    fake_consts = SimpleNamespace(TIMEOUT_DURATION=0.1)
    fake_flapi = SimpleNamespace(
        _consts=fake_consts,
        enable=lambda: calls.append("enable") or True,
        fl_exec=lambda code: calls.append(("exec", code)),
        fl_eval=lambda expression: calls.append(("eval", expression)) or {"ok": True},
        disable=lambda: calls.append("disable"),
    )
    monkeypatch.setitem(sys.modules, "flapi", fake_flapi)
    monkeypatch.delitem(sys.modules, "flapi.client", raising=False)

    client = default_client_factory()
    client.exec("x = 1")
    result = client.eval("x")
    client.close()

    assert result == {"ok": True}
    assert calls == ["enable", ("exec", "x = 1"), ("eval", "x"), "disable"]
    assert fake_consts.TIMEOUT_DURATION == 3.0


def test_default_client_factory_sets_timeout_before_enabling_flapi(monkeypatch):
    calls = []
    fake_consts = SimpleNamespace(TIMEOUT_DURATION=0.1)

    def enable():
        calls.append(("enable", fake_consts.TIMEOUT_DURATION))
        return True

    fake_flapi = SimpleNamespace(
        _consts=fake_consts,
        enable=enable,
        fl_exec=lambda code: None,
        fl_eval=lambda expression: None,
        disable=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "flapi", fake_flapi)

    default_client_factory()

    assert calls == [("enable", 3.0)]


def test_default_client_factory_closes_flapi_ports_when_enable_fails(monkeypatch):
    calls = []
    req_port = SimpleNamespace(close=lambda: calls.append("close request"))
    res_port = SimpleNamespace(close=lambda: calls.append("close response"))
    fake_context = SimpleNamespace(
        req_port=req_port,
        res_port=res_port,
        functions_backup={"mixer": {}},
    )
    fake_flapi = SimpleNamespace(
        _consts=SimpleNamespace(TIMEOUT_DURATION=0.1),
        enable=lambda: False,
    )
    fake_context_module = SimpleNamespace(
        pop_context=lambda: calls.append("pop context") or fake_context,
    )
    fake_decorate_module = SimpleNamespace(
        restore_original_functions=lambda backup: calls.append(("restore", backup)),
    )
    monkeypatch.setitem(sys.modules, "flapi", fake_flapi)
    monkeypatch.setitem(sys.modules, "flapi.__context", fake_context_module)
    monkeypatch.setitem(sys.modules, "flapi.__decorate", fake_decorate_module)

    with pytest.raises(RuntimeError):
        default_client_factory()

    assert calls == [
        "pop context",
        "close request",
        "close response",
        ("restore", {"mixer": {}}),
    ]


def test_probe_bridge_serializes_flapi_access(monkeypatch):
    calls = []

    class FakeLock:
        def __enter__(self):
            calls.append("lock enter")

        def __exit__(self, exc_type, exc, traceback):
            calls.append("lock exit")

    class FakeClient:
        def exec(self, code):
            calls.append("exec")

        def eval(self, expression):
            values = {
                '__fl_connector_bridge_snapshot__["flVersion"]': "Producer Edition v2025",
                '__fl_connector_bridge_snapshot__["projectTitle"]': "Locked project",
                '__fl_connector_bridge_snapshot__["selectedTrack"]': 0,
                '__fl_connector_bridge_snapshot__["trackCount"]': 0,
                '__fl_connector_bridge_snapshot__["transport"]': {
                    "playing": False,
                    "recording": False,
                    "loopMode": 0,
                    "songPosition": 0.0,
                    "songPositionHint": "",
                    "songLengthBars": None,
                    "tempo": None,
                },
                'len(__fl_connector_bridge_snapshot__["tracks"])': 0,
                '__fl_connector_bridge_snapshot__["errors"]': [],
            }
            return values[expression]

        def close(self):
            calls.append("close")

    monkeypatch.setattr(bridge_module, "_BRIDGE_PROBE_LOCK", FakeLock())

    snapshot = probe_bridge(client_factory=FakeClient)

    assert snapshot.status == "connected"
    assert calls == ["lock enter", "exec", "close", "lock exit"]


def test_run_transport_action_starts_playback_and_returns_snapshot():
    calls = []

    class FakeClient:
        def exec(self, code):
            calls.append(("exec", code))

        def eval(self, expression):
            values = {
                '__fl_connector_bridge_snapshot__["flVersion"]': "Producer Edition v2025",
                '__fl_connector_bridge_snapshot__["projectTitle"]': "Action project",
                '__fl_connector_bridge_snapshot__["selectedTrack"]': 0,
                '__fl_connector_bridge_snapshot__["trackCount"]': 1,
                '__fl_connector_bridge_snapshot__["transport"]': {
                    "playing": True,
                    "recording": False,
                    "loopMode": 0,
                    "songPosition": 0.0,
                    "songPositionHint": "1:01:000",
                    "songLengthBars": 4,
                    "tempo": 114000,
                },
                'len(__fl_connector_bridge_snapshot__["tracks"])': 0,
                '__fl_connector_bridge_snapshot__["errors"]': [],
            }
            return values[expression]

        def close(self):
            calls.append(("close", None))

    snapshot = run_transport_action("play", client_factory=FakeClient)

    assert snapshot.status == "connected"
    assert snapshot.message == "Live FL transport action applied: play."
    assert snapshot.transport is not None
    assert snapshot.transport.playing is True
    assert snapshot.transport.tempo == 114.0
    assert calls == [
        ("exec", "import transport\ntransport.start()"),
        ("exec", READ_ONLY_FL_PROBE),
        ("close", None),
    ]


def test_run_transport_action_stops_playback_and_returns_snapshot():
    class FakeClient:
        def exec(self, code):
            self.last_code = code

        def eval(self, expression):
            values = {
                '__fl_connector_bridge_snapshot__["flVersion"]': "Producer Edition v2025",
                '__fl_connector_bridge_snapshot__["projectTitle"]': "Stopped project",
                '__fl_connector_bridge_snapshot__["selectedTrack"]': 0,
                '__fl_connector_bridge_snapshot__["trackCount"]': 0,
                '__fl_connector_bridge_snapshot__["transport"]': {
                    "playing": False,
                    "recording": False,
                    "loopMode": 0,
                    "songPosition": 0.0,
                    "songPositionHint": "1:01:000",
                    "songLengthBars": 4,
                    "tempo": 114.0,
                },
                'len(__fl_connector_bridge_snapshot__["tracks"])': 0,
                '__fl_connector_bridge_snapshot__["errors"]': [],
            }
            return values[expression]

        def close(self):
            self.closed = True

    snapshot = run_transport_action("stop", client_factory=FakeClient)

    assert snapshot.status == "connected"
    assert snapshot.transport is not None
    assert snapshot.transport.playing is False


def test_run_transport_action_rejects_unsupported_actions():
    with pytest.raises(ValueError):
        run_transport_action("record", client_factory=lambda: object())


def test_bridge_transport_endpoint_runs_action(monkeypatch):
    calls = []
    snapshot = BridgeSnapshot.from_dict(
        {
            "status": "connected",
            "message": "Live FL transport action applied: play.",
            "source": "flapi",
            "flVersion": "Producer Edition v2025",
            "projectTitle": "Endpoint project",
            "selectedTrack": 0,
            "trackCount": 0,
            "transport": {
                "playing": True,
                "recording": False,
                "loopMode": 0,
                "songPosition": 0.0,
                "songPositionHint": "1:01:000",
                "songLengthBars": 4,
                "tempo": 114.0,
            },
            "tracks": [],
            "setup": [],
            "errors": [],
        }
    )
    monkeypatch.setattr(
        main_module,
        "run_transport_action",
        lambda action: calls.append(action) or snapshot,
    )

    body = main_module.bridge_transport(main_module.BridgeTransportRequest(action="play"))

    assert calls == ["play"]
    assert body["status"] == "connected"
    assert body["transport"]["playing"] is True


def test_bridge_probe_builds_connected_snapshot_from_client_response():
    class FakeClient:
        def exec(self, code):
            assert code == READ_ONLY_FL_PROBE

        def eval(self, expression):
            values = {
                '__fl_connector_bridge_snapshot__["flVersion"]': "Producer Edition v2025",
                '__fl_connector_bridge_snapshot__["projectTitle"]': "Untitled - FL Studio",
                '__fl_connector_bridge_snapshot__["selectedTrack"]': 2,
                '__fl_connector_bridge_snapshot__["trackCount"]': 4,
                '__fl_connector_bridge_snapshot__["transport"]': {
                    "playing": True,
                    "recording": False,
                    "loopMode": 1,
                    "songPosition": 4.0,
                    "songPositionHint": "2:01:000",
                    "songLengthBars": 16,
                    "tempo": 113.0,
                },
                'len(__fl_connector_bridge_snapshot__["tracks"])': 1,
                '__fl_connector_bridge_snapshot__["tracks"][0]': {
                    "index": 2,
                    "name": "Bass",
                    "volume": 0.67,
                    "pan": 0.5,
                    "selected": True,
                    "slots": ["Fruity Parametric EQ 2"],
                },
                '__fl_connector_bridge_snapshot__["errors"]': [],
            }
            return values[expression]

        def close(self):
            self.closed = True

    snapshot = probe_bridge(client_factory=FakeClient)

    assert snapshot.status == "connected"
    assert snapshot.selectedTrack == 2
    assert snapshot.transport is not None
    assert snapshot.transport.playing is True
    assert snapshot.tracks[0].slots == ["Fruity Parametric EQ 2"]


def test_bridge_probe_reads_snapshot_in_chunks_to_avoid_large_midi_responses():
    class FakeClient:
        def exec(self, code):
            assert code == READ_ONLY_FL_PROBE

        def eval(self, expression):
            assert expression != "__fl_connector_bridge_snapshot__"
            values = {
                '__fl_connector_bridge_snapshot__["flVersion"]': "Producer Edition v2025",
                '__fl_connector_bridge_snapshot__["projectTitle"]': "Chunked project",
                '__fl_connector_bridge_snapshot__["selectedTrack"]': 0,
                '__fl_connector_bridge_snapshot__["trackCount"]': 2,
                '__fl_connector_bridge_snapshot__["transport"]': {
                    "playing": False,
                    "recording": False,
                    "loopMode": 0,
                    "songPosition": 0.0,
                    "songPositionHint": "1:01:000",
                    "songLengthBars": 8,
                    "tempo": 113.0,
                },
                'len(__fl_connector_bridge_snapshot__["tracks"])': 2,
                '__fl_connector_bridge_snapshot__["tracks"][0]': {
                    "index": 0,
                    "name": "Master",
                    "volume": 0.8,
                    "pan": 0.0,
                    "selected": True,
                    "slots": ["Emphasizer"],
                },
                '__fl_connector_bridge_snapshot__["tracks"][1]': {
                    "index": 1,
                    "name": "Keys",
                    "volume": 0.7,
                    "pan": 0.5,
                    "selected": False,
                    "slots": [],
                },
                '__fl_connector_bridge_snapshot__["errors"]': [],
            }
            return values[expression]

        def close(self):
            self.closed = True

    snapshot = probe_bridge(client_factory=FakeClient)

    assert snapshot.status == "connected"
    assert snapshot.projectTitle == "Chunked project"
    assert [track.name for track in snapshot.tracks] == ["Master", "Keys"]


def test_bridge_probe_reports_chunk_eval_errors():
    class FakeClient:
        def exec(self, code):
            assert code == READ_ONLY_FL_PROBE

        def eval(self, expression):
            if expression == '__fl_connector_bridge_snapshot__["flVersion"]':
                raise TimeoutError("chunk timed out")
            return None

        def close(self):
            self.closed = True

    snapshot = probe_bridge(client_factory=FakeClient)

    assert snapshot.status == "error"
    assert snapshot.errors == ["chunk timed out"]


def test_bridge_probe_handles_empty_tracks():
    class FakeClient:
        def exec(self, code):
            assert code == READ_ONLY_FL_PROBE

        def eval(self, expression):
            values = {
                '__fl_connector_bridge_snapshot__["flVersion"]': "Producer Edition v2025",
                '__fl_connector_bridge_snapshot__["projectTitle"]': "Empty project",
                '__fl_connector_bridge_snapshot__["selectedTrack"]': None,
                '__fl_connector_bridge_snapshot__["trackCount"]': 0,
                '__fl_connector_bridge_snapshot__["transport"]': {
                    "playing": False,
                    "recording": False,
                    "loopMode": 0,
                    "songPosition": 0.0,
                    "songPositionHint": "",
                    "songLengthBars": None,
                    "tempo": None,
                },
                'len(__fl_connector_bridge_snapshot__["tracks"])': 0,
                '__fl_connector_bridge_snapshot__["errors"]': [],
            }
            return values[expression]

        def close(self):
            self.closed = True

    snapshot = probe_bridge(client_factory=FakeClient)

    assert snapshot.status == "connected"
    assert snapshot.tracks == []


def test_bridge_probe_normalizes_fl_studio_scaled_tempo():
    class FakeClient:
        def exec(self, code):
            assert code == READ_ONLY_FL_PROBE

        def eval(self, expression):
            values = {
                '__fl_connector_bridge_snapshot__["flVersion"]': "Producer Edition v2025",
                '__fl_connector_bridge_snapshot__["projectTitle"]': "Scaled tempo project",
                '__fl_connector_bridge_snapshot__["selectedTrack"]': 0,
                '__fl_connector_bridge_snapshot__["trackCount"]': 1,
                '__fl_connector_bridge_snapshot__["transport"]': {
                    "playing": False,
                    "recording": False,
                    "loopMode": 0,
                    "songPosition": 0.0,
                    "songPositionHint": "1:01:000",
                    "songLengthBars": 4,
                    "tempo": 130000,
                },
                'len(__fl_connector_bridge_snapshot__["tracks"])': 0,
                '__fl_connector_bridge_snapshot__["errors"]': [],
            }
            return values[expression]

        def close(self):
            self.closed = True

    snapshot = probe_bridge(client_factory=FakeClient)

    assert snapshot.status == "connected"
    assert snapshot.transport is not None
    assert snapshot.transport.tempo == 130.0


def test_bridge_probe_uses_tracks_returned_by_probe_even_when_fl_track_count_is_larger():
    class FakeClient:
        def exec(self, code):
            assert code == READ_ONLY_FL_PROBE

        def eval(self, expression):
            values = {
                '__fl_connector_bridge_snapshot__["flVersion"]': "Producer Edition v2025",
                '__fl_connector_bridge_snapshot__["projectTitle"]': "Limited project",
                '__fl_connector_bridge_snapshot__["selectedTrack"]': 3,
                '__fl_connector_bridge_snapshot__["trackCount"]': 99,
                '__fl_connector_bridge_snapshot__["transport"]': {
                    "playing": False,
                    "recording": False,
                    "loopMode": 0,
                    "songPosition": 0.0,
                    "songPositionHint": "1:01:000",
                    "songLengthBars": 4,
                    "tempo": 120.0,
                },
                'len(__fl_connector_bridge_snapshot__["tracks"])': 1,
                '__fl_connector_bridge_snapshot__["tracks"][0]': {
                    "index": 3,
                    "name": "Only fetched track",
                    "volume": 0.5,
                    "pan": 0.5,
                    "selected": True,
                    "slots": [],
                },
                '__fl_connector_bridge_snapshot__["errors"]': [],
            }
            return values[expression]

        def close(self):
            self.closed = True

    snapshot = probe_bridge(client_factory=FakeClient)

    assert snapshot.status == "connected"
    assert snapshot.trackCount == 99
    assert [track.name for track in snapshot.tracks] == ["Only fetched track"]


def test_read_only_probe_does_not_include_write_actions():
    banned_calls = [
        "transport.start(",
        "transport.stop(",
        "transport.record(",
        "transport.set",
        "mixer.set",
        "mixer.select",
        "plugins.set",
        "ui.set",
    ]

    for call in banned_calls:
        assert call not in READ_ONLY_FL_PROBE


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
