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
