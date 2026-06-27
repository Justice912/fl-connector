import pytest

from app.harmony import GENRE_HARMONY, build_chords, chord_roots

# A minor scale pitch classes: A(9) B(11) C(0) D(2) E(4) F(5) G(7)
_A_MINOR_PCS = {9, 11, 0, 2, 4, 5, 7}


def test_build_chords_is_in_key_and_in_range():
    for family in ("amapiano", "afro", "hiphop"):
        notes = build_chords(family, "A", "minor", bars=4)
        assert notes, family
        for note in notes:
            assert 0 <= note.pitch <= 127
            assert note.pitch % 12 in _A_MINOR_PCS, (family, note.pitch)
            note.validate()


def test_build_chords_count_matches_voicing_times_bars():
    for family, harmony in GENRE_HARMONY.items():
        notes = build_chords(family, "A", "minor", bars=4)
        assert len(notes) == 4 * len(harmony.voicing), family


def test_chord_roots_follow_progression_and_cycle():
    roots = chord_roots("hiphop", "A", "minor", bars=6)
    assert len(roots) == 6
    assert roots[0] == roots[4]   # progression cycles every 4 bars
    assert roots[1] == roots[5]
    assert roots[0] != roots[1]   # ii -> v is real harmonic movement


def test_genres_produce_distinct_chords():
    sets = {
        family: tuple(sorted(n.pitch for n in build_chords(family, "A", "minor", bars=4)))
        for family in ("amapiano", "afro", "hiphop")
    }
    assert sets["amapiano"] != sets["afro"]
    assert sets["amapiano"] != sets["hiphop"]
    assert sets["afro"] != sets["hiphop"]


def test_build_chords_is_deterministic():
    a = build_chords("amapiano", "A", "minor", bars=4)
    b = build_chords("amapiano", "A", "minor", bars=4)
    assert [n.to_dict() for n in a] == [n.to_dict() for n in b]


def test_chords_stay_within_bar_length():
    bars = 4
    for family in ("amapiano", "afro", "hiphop"):
        for note in build_chords(family, "A", "minor", bars=bars):
            assert note.startBeats + note.durationBeats <= bars * 4 + 0.001


def test_unknown_family_raises_and_zero_bars_empty():
    assert build_chords("amapiano", "A", "minor", bars=0) == []
    assert chord_roots("amapiano", "A", "minor", bars=0) == []
    with pytest.raises(ValueError):
        build_chords("nope", "A", "minor", bars=4)
    with pytest.raises(ValueError):
        chord_roots("nope", "A", "minor", bars=4)
