import math

import pytest

from app.extension_plan import (
    GENRE_TEMPLATES,
    build_extension_plan,
    choose_loop_window,
    render_layout,
    samples_per_bar,
)


def test_templates_only_reference_known_roles():
    from app.extension_plan import KNOWN_ROLES
    for rows in GENRE_TEMPLATES.values():
        for _name, _weight, roles, _is_main in rows:
            assert set(roles) <= KNOWN_ROLES


def test_plan_hits_target_window_and_orders_sections():
    plan = build_extension_plan(
        genre="amapiano", tempo_bpm=112.0, loop_bars=16, target_seconds=390.0,
        roles=["drums", "bass", "chords", "melody", "vocals", "percussion", "log_drum"],
        vocal_seconds=200.0,
    )
    assert [s.name for s in plan.sections] == ["Intro", "Build", "Main", "Breakdown", "Drop", "Outro"]
    assert 360.0 <= plan.total_seconds() <= 420.0
    # every section length is a whole number of loop phrases
    assert all(s.bars % 16 == 0 for s in plan.sections)


def test_main_block_tracks_vocal_length():
    plan = build_extension_plan(
        genre="amapiano", tempo_bpm=120.0, loop_bars=8, target_seconds=390.0,
        roles=["drums", "bass", "vocals"], vocal_seconds=96.0,  # 96s @120bpm = 48 bars
    )
    # main block (is_main sections combined) ~ vocal length in bars, rounded to loop_bars
    main_bars = sum(s.bars for s in plan.sections if s.is_main)
    assert abs(main_bars - 48) <= 8


def test_unknown_genre_falls_back_to_amapiano():
    a = build_extension_plan(genre="techno", tempo_bpm=120.0, loop_bars=16,
                             target_seconds=390.0, roles=["drums", "bass"], vocal_seconds=None)
    b = build_extension_plan(genre="amapiano", tempo_bpm=120.0, loop_bars=16,
                             target_seconds=390.0, roles=["drums", "bass"], vocal_seconds=None)
    assert [s.name for s in a.sections] == [s.name for s in b.sections]


def test_active_roles_filtered_to_present_stems():
    plan = build_extension_plan(
        genre="amapiano", tempo_bpm=112.0, loop_bars=16, target_seconds=390.0,
        roles=["drums", "bass"], vocal_seconds=None,
    )
    for section in plan.sections:
        assert set(section.active_roles) <= {"drums", "bass"}


def test_choose_loop_window_is_in_steady_middle():
    start = choose_loop_window(total_bars=64, loop_bars=16)
    assert 16 <= start <= 64 - 16 + 1  # not the first or last phrase, fits within the song


def test_choose_loop_window_clamps_for_short_songs():
    assert choose_loop_window(total_bars=10, loop_bars=16) == 1


def test_samples_per_bar_matches_tempo():
    assert samples_per_bar(120.0, 44100) == round(44100 * 240 / 120.0)


def test_render_layout_is_contiguous_and_covers_total():
    plan = build_extension_plan(
        genre="amapiano", tempo_bpm=120.0, loop_bars=16, target_seconds=390.0,
        roles=["drums", "bass", "vocals"], vocal_seconds=120.0,
    )
    spb = samples_per_bar(120.0, 44100)
    layout = render_layout(plan, spb)
    assert layout[0][0] == 0
    for (s0, e0, *_), (s1, *_rest) in zip(layout, layout[1:]):
        assert e0 == s1  # contiguous
    assert layout[-1][1] == plan.total_bars() * spb
