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


def test_groove_shifts_notes_off_the_rigid_grid():
    # The rigid builders place notes on exact 0.25-beat multiples; the groove pass
    # (swing + jitter) must move at least some notes off that grid.
    payload = generate_payload(prompt="Create a deep amapiano log drum riff", key="A")
    off_grid = [n for n in payload.notes if abs(((n.startBeats * 4) % 1.0)) > 1e-6]
    assert off_grid, "expected groove to shift some notes off the 0.25-beat grid"


def test_groove_preserves_note_count_and_determinism():
    first = generate_payload(prompt="Create a deep amapiano log drum riff", key="A")
    second = generate_payload(prompt="Create a deep amapiano log drum riff", key="A")
    # determinism (seeded from stable inputs) is preserved
    assert [n.to_dict() for n in first.notes] == [n.to_dict() for n in second.notes]
    # every note still satisfies the contract after grooving
    for note in first.notes:
        note.validate()


def test_amapiano_song_chords_use_extended_voicing():
    # amapiano 9th voicing = 5 sustained tones per bar; the chords role is never swung,
    # so each chord stays on its exact bar boundary.
    draft = generate_song_draft(prompt="deep amapiano song", genre="Amapiano", key="A", scale="minor", bars=4)
    chords = next(p for p in draft.parts if p.role == "chords")
    per_bar: dict[int, int] = {}
    for n in chords.payload.notes:
        per_bar[int(n.startBeats // 4)] = per_bar.get(int(n.startBeats // 4), 0) + 1
    assert per_bar and all(count == 5 for count in per_bar.values())


def test_amapiano_song_bass_follows_progression():
    # progression i-VI-III-VII is not constant, so the per-bar bass root must move.
    draft = generate_song_draft(prompt="deep amapiano song", genre="Amapiano", key="A", scale="minor", bars=4)
    bass = next(p for p in draft.parts if p.role == "bass")
    bar_min: dict[int, int] = {}
    for n in bass.payload.notes:
        bar = int(n.startBeats // 4)
        bar_min[bar] = min(bar_min.get(bar, 999), n.pitch)
    assert len(set(bar_min.values())) > 1, "bass should follow the progression, not stay on tonic"


def test_genres_have_distinct_chord_pitches():
    def chord_pitches(genre):
        draft = generate_song_draft(prompt=f"{genre} song", genre=genre, key="A", scale="minor", bars=4)
        chords = next(p for p in draft.parts if p.role == "chords")
        return tuple(sorted(n.pitch for n in chords.payload.notes))
    ama = chord_pitches("Amapiano")
    afro = chord_pitches("Afrobeats")
    hh = chord_pitches("Hip Hop")
    assert ama != afro
    assert ama != hh
    assert afro != hh


def test_afro_and_hiphop_bass_follow_progression():
    for genre in ("Afrobeats", "Hip Hop"):
        draft = generate_song_draft(prompt=f"{genre} song", genre=genre, key="A", scale="minor", bars=4)
        bass = next(p for p in draft.parts if p.role == "bass")
        bar_min: dict[int, int] = {}
        for n in bass.payload.notes:
            bar = int(n.startBeats // 4)
            bar_min[bar] = min(bar_min.get(bar, 999), n.pitch)
        assert len(set(bar_min.values())) > 1, f"{genre} bass should follow the progression"
