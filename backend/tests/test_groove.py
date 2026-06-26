import pytest

from app.contracts import Note
from app.groove import (
    GROOVE_TEMPLATES,
    GrooveTemplate,
    apply_groove,
    groove_seed,
)


def _note(start, velocity=0.6):
    return Note(pitch=60, startBeats=start, durationBeats=0.25, velocity=velocity, color=2)


def test_swing_delays_offbeat_by_swing_times_grid(monkeypatch):
    # zero jitter so swing is isolated and exact
    monkeypatch.setitem(
        GROOVE_TEMPLATES, "_t", GrooveTemplate(swing=0.5, swing_grid=0.5, timing_jitter=0.0, velocity_jitter=0.0)
    )
    # offbeat of an 8th grid (0.5) is at 0.5, 1.5, ...
    out = apply_groove([_note(0.5)], family="_t", role="drums", seed=1)
    assert out[0].startBeats == 0.75  # 0.5 + swing(0.5)*grid(0.5)


def test_onbeat_is_unchanged_under_zero_jitter(monkeypatch):
    monkeypatch.setitem(
        GROOVE_TEMPLATES, "_t", GrooveTemplate(swing=0.5, swing_grid=0.5, timing_jitter=0.0, velocity_jitter=0.0)
    )
    out = apply_groove([_note(1.0)], family="_t", role="drums", seed=1)
    assert out[0].startBeats == 1.0


def test_chords_are_not_swung_and_timing_unchanged(monkeypatch):
    monkeypatch.setitem(
        GROOVE_TEMPLATES, "_t", GrooveTemplate(swing=0.5, swing_grid=0.5, timing_jitter=0.05, velocity_jitter=0.0)
    )
    out = apply_groove([_note(0.5)], family="_t", role="chords", seed=1)
    assert out[0].startBeats == 0.5  # no swing (offbeat), no timing jitter for chords


def test_velocity_and_start_are_clamped_and_valid():
    notes = [Note(pitch=60, startBeats=0.0, durationBeats=0.25, velocity=0.99, color=2) for _ in range(50)]
    out = apply_groove(notes, family="amapiano", role="drums", seed=7)
    for note in out:
        assert 0.05 <= note.velocity <= 1.0
        assert note.startBeats >= 0.0
        note.validate()  # contract still satisfied


def test_same_inputs_are_deterministic_and_seed_changes_output():
    notes = [_note(i * 0.5) for i in range(8)]
    a = apply_groove(notes, family="amapiano", role="drums", seed=42)
    b = apply_groove(notes, family="amapiano", role="drums", seed=42)
    c = apply_groove(notes, family="amapiano", role="drums", seed=43)
    assert [n.to_dict() for n in a] == [n.to_dict() for n in b]
    assert [n.to_dict() for n in a] != [n.to_dict() for n in c]


def test_groove_seed_is_stable_and_role_sensitive():
    s1 = groove_seed("deep amapiano", "A", 8, "Amapiano", "drums")
    s2 = groove_seed("deep amapiano", "A", 8, "Amapiano", "drums")
    s3 = groove_seed("deep amapiano", "A", 8, "Amapiano", "bass")
    assert s1 == s2
    assert s1 != s3
    assert isinstance(s1, int)


def test_unknown_family_raises_and_empty_list_returns_empty():
    assert apply_groove([], family="amapiano", role="drums", seed=1) == []
    with pytest.raises(ValueError):
        apply_groove([_note(0.5)], family="nope", role="drums", seed=1)
