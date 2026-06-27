import pytest

from app.contracts import Note
from app.fills import FILL_TEMPLATES, apply_fills


def _steady_drums(bars):
    # kick on beat 0 (outside the fill window) + a unique marker hit (pitch 99) in the
    # last-beat window [3.0,4.0) of every bar, so removal is unambiguous.
    notes = []
    for bar in range(bars):
        base = bar * 4
        notes.append(Note(36, base + 0.0, 0.2, 0.9, 5))
        notes.append(Note(99, base + 3.5, 0.1, 0.5, 2))
    return notes


def test_fill_bars_selected_for_various_lengths():
    # amapiano fill introduces shaker pitch 70, which the base pattern never uses,
    # so pitch-70 bars mark exactly the filled bars.
    def filled_bars(bars):
        out = apply_fills(_steady_drums(bars), family="amapiano", bars=bars)
        return sorted({int(n.startBeats // 4) for n in out if n.pitch == 70})
    assert filled_bars(4) == [3]
    assert filled_bars(8) == [3, 7]
    assert filled_bars(2) == [1]   # final-bar rule when no full phrase boundary


def test_window_base_hits_removed_only_on_fill_bars():
    out = apply_fills(_steady_drums(8), family="afro", bars=8)
    # the marker (99) in the window survives on non-fill bars, is removed on fill bars 3 & 7
    assert sorted({int(n.startBeats // 4) for n in out if n.pitch == 99}) == [0, 1, 2, 4, 5, 6]
    # the beat-0 kick (outside the window) survives on every bar, incl. fill bar 3 (start 12.0)
    assert any(n.pitch == 36 and abs(n.startBeats - 12.0) < 1e-9 for n in out)


def test_non_fill_bars_are_byte_identical_to_input():
    base = _steady_drums(8)
    out = apply_fills(base, family="amapiano", bars=8)
    base_non_fill = [n.to_dict() for n in base if int(n.startBeats // 4) not in {3, 7}]
    out_non_fill = [n.to_dict() for n in out if int(n.startBeats // 4) not in {3, 7}]
    assert out_non_fill == base_non_fill


def test_genres_produce_distinct_fills():
    base = _steady_drums(4)
    sets = {
        fam: tuple(sorted((n.pitch, n.startBeats, n.velocity) for n in apply_fills(base, family=fam, bars=4)))
        for fam in ("amapiano", "afro", "hiphop")
    }
    assert sets["amapiano"] != sets["afro"]
    assert sets["amapiano"] != sets["hiphop"]
    assert sets["afro"] != sets["hiphop"]


def test_deterministic_and_input_not_mutated():
    base = _steady_drums(8)
    snapshot = [n.to_dict() for n in base]
    a = apply_fills(base, family="hiphop", bars=8)
    b = apply_fills(base, family="hiphop", bars=8)
    assert [n.to_dict() for n in a] == [n.to_dict() for n in b]
    assert [n.to_dict() for n in base] == snapshot  # input list untouched


def test_fill_notes_valid_and_within_bar():
    out = apply_fills(_steady_drums(8), family="amapiano", bars=8)
    for n in out:
        n.validate()
        bar = int(n.startBeats // 4)
        assert n.startBeats + n.durationBeats <= bar * 4 + 4.0 + 1e-9


def test_unknown_family_raises_and_empty_returns_empty():
    assert apply_fills([], family="amapiano", bars=4) == []
    assert apply_fills([], family="nope", bars=4) == []
    with pytest.raises(ValueError):
        apply_fills(_steady_drums(4), family="nope", bars=4)
