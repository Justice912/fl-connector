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
