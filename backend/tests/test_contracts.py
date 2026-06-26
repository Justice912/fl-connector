import pytest

from app.contracts import ContractError, Note, NotePayload, validate_payload_dict


def test_valid_payload_round_trips():
    payload = NotePayload.create(
        title="Test",
        sourcePrompt="Create a riff",
        genre="Amapiano",
        bpm=113,
        key="A",
        scale="minor",
        bars=1,
        notes=[Note(pitch=69, startBeats=0, durationBeats=1)],
    )

    assert validate_payload_dict(payload.to_dict())["notes"][0]["pitch"] == 69


def test_rejects_bad_velocity():
    with pytest.raises(ContractError):
        Note(pitch=60, startBeats=0, durationBeats=1, velocity=1.5).validate()


def test_rejects_notes_beyond_bars():
    with pytest.raises(ContractError):
        NotePayload.create(
            title="Bad",
            sourcePrompt="Too long",
            genre="Amapiano",
            bpm=113,
            key="A",
            scale="minor",
            bars=1,
            notes=[Note(pitch=60, startBeats=3.9, durationBeats=1)],
        )


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
