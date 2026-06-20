from app.generator import generate_payload, generate_song_draft


def test_amapiano_generation_is_valid_and_deterministic():
    first = generate_payload(prompt="Create a deep amapiano log drum riff", key="A")
    second = generate_payload(prompt="Create a deep amapiano log drum riff", key="A")

    assert first.bpm == 113
    assert first.genre == "Amapiano"
    assert len(first.notes) == len(second.notes)
    assert [note.to_dict() for note in first.notes] == [note.to_dict() for note in second.notes]
    assert any(note.color == 2 for note in first.notes)
    assert any(note.color == 5 for note in first.notes)


def test_song_draft_creates_applyable_parts():
    draft = generate_song_draft(
        prompt="Create an 8-bar deep amapiano song draft",
        genre="Amapiano",
        bpm=113,
        key="A",
        scale="minor",
        bars=8,
    )

    roles = [part.role for part in draft.parts]
    assert roles == ["drums", "bass", "chords", "log_drum", "melody"]
    assert len(draft.arrangement) == 4
    assert all(part.payload.target == "current_piano_roll" for part in draft.parts)
    assert all(part.payload.status == "draft" for part in draft.parts)
    assert sum(len(part.payload.notes) for part in draft.parts) > 100
