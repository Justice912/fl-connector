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
