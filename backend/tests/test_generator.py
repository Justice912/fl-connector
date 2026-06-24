import pytest

from app.generator import generate_payload, generate_song_draft, genre_family


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


@pytest.mark.parametrize("genre", ["Amapiano", "Afrobeats", "Afrohouse", "Hip Hop", "Trap"])
def test_song_draft_parts_and_arrangement_are_coherent(genre):
    draft = generate_song_draft(prompt=f"Create a {genre} song", genre=genre, bars=8)
    roles = {part.role for part in draft.parts}
    assert len(draft.parts) >= 4
    assert len(draft.arrangement) == 4
    assert all(len(part.payload.notes) > 0 for part in draft.parts)
    assert [part.applyOrder for part in draft.parts] == list(range(1, len(draft.parts) + 1))
    for section in draft.arrangement:
        assert section.activeParts, "arrangement section must list active parts"
        assert set(section.activeParts) <= roles


def test_trap_uses_same_family_for_single_and_song():
    assert genre_family("Trap") == genre_family("Hip Hop") == "hiphop"
    draft = generate_song_draft(prompt="dark trap song", genre="Trap")
    assert {part.role for part in draft.parts} == {"drums", "bass", "chords", "melody"}
