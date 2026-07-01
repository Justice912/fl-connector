from __future__ import annotations

from dataclasses import dataclass
from typing import Any

KNOWN_ROLES = frozenset(
    {"drums", "percussion", "bass", "chords", "log_drum", "melody", "vocals", "guitar", "fx", "other"}
)

# (name, weight, active_roles, is_main). weight>0 => instrumental sized by weight;
# weight==0 => a "main" block sized to the vocal length.
GENRE_TEMPLATES: dict[str, list[tuple[str, int, list[str], bool]]] = {
    "amapiano": [
        ("Intro", 2, ["drums", "percussion"], False),
        ("Build", 2, ["drums", "percussion", "bass", "log_drum"], False),
        ("Main", 0, ["drums", "percussion", "bass", "log_drum", "chords", "melody", "vocals"], True),
        ("Breakdown", 1, ["chords", "melody"], False),
        ("Drop", 0, ["drums", "percussion", "bass", "log_drum", "chords", "melody", "vocals"], True),
        ("Outro", 2, ["drums", "bass"], False),
    ],
    "deep_house": [
        ("Intro", 2, ["drums"], False),
        ("Build", 2, ["drums", "bass", "chords"], False),
        ("Main", 0, ["drums", "bass", "chords", "melody", "vocals"], True),
        ("Breakdown", 1, ["chords", "melody"], False),
        ("Drop", 0, ["drums", "bass", "chords", "melody", "vocals"], True),
        ("Outro", 2, ["drums", "bass"], False),
    ],
}


def _validate_tables() -> None:
    for genre, rows in GENRE_TEMPLATES.items():
        for name, _weight, roles, _is_main in rows:
            invalid = set(roles) - KNOWN_ROLES
            if invalid:
                raise ValueError(f"{genre} template section {name} has unknown roles: {sorted(invalid)}")


_validate_tables()


@dataclass(frozen=True)
class ExtensionSection:
    name: str
    bars: int
    active_roles: list[str]
    is_main: bool

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "bars": self.bars, "activeRoles": self.active_roles, "isMain": self.is_main}


@dataclass(frozen=True)
class ExtensionPlan:
    sections: list[ExtensionSection]
    loop_bars: int
    tempo_bpm: float

    def total_bars(self) -> int:
        return sum(section.bars for section in self.sections)

    def total_seconds(self) -> float:
        return self.total_bars() * 240.0 / self.tempo_bpm

    def main_bars(self) -> int:
        return sum(section.bars for section in self.sections if section.is_main)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sections": [section.to_dict() for section in self.sections],
            "loopBars": self.loop_bars,
            "tempoBpm": self.tempo_bpm,
            "totalBars": self.total_bars(),
            "totalSeconds": round(self.total_seconds(), 3),
        }


def samples_per_bar(tempo_bpm: float, sample_rate: int) -> int:
    return round(sample_rate * 240.0 / tempo_bpm)


def _round_to(value: int, multiple: int) -> int:
    return max(multiple, round(value / multiple) * multiple)


def build_extension_plan(
    *,
    genre: str,
    tempo_bpm: float,
    loop_bars: int,
    target_seconds: float,
    roles: list[str],
    vocal_seconds: float | None,
) -> ExtensionPlan:
    template = GENRE_TEMPLATES.get(genre, GENRE_TEMPLATES["amapiano"])
    bar_seconds = 240.0 / tempo_bpm
    target_bars = _round_to(round(target_seconds / bar_seconds), loop_bars)

    # Main block ~ vocal length (or a default of 32 bars), split across the is_main sections.
    default_main_bars = 32
    main_source_bars = round((vocal_seconds / bar_seconds)) if vocal_seconds else default_main_bars
    main_total = _round_to(main_source_bars, loop_bars)
    main_sections = [row for row in template if row[3]]
    per_main = _round_to(main_total // max(1, len(main_sections)), loop_bars)

    # Remaining bars go to instrumental sections, distributed by weight.
    instrumental = [row for row in template if not row[3]]
    weight_total = sum(row[1] for row in instrumental) or 1
    remaining = max(loop_bars * len(instrumental), target_bars - per_main * len(main_sections))

    present = set(roles)
    sections: list[ExtensionSection] = []
    for name, weight, active, is_main in template:
        if is_main:
            bars = per_main
        else:
            bars = _round_to(round(remaining * weight / weight_total), loop_bars)
        filtered = [role for role in active if role in present]
        sections.append(ExtensionSection(name=name, bars=bars, active_roles=filtered, is_main=is_main))

    # Guarantee the total lands in the accepted 360-420 s window by nudging instrumental
    # sections by whole loop phrases (rounding-down above can otherwise fall short).
    bar_seconds = 240.0 / tempo_bpm

    def _seconds(secs: list[ExtensionSection]) -> float:
        return sum(s.bars for s in secs) * bar_seconds

    def _bump(index: int, delta: int) -> None:
        s = sections[index]
        sections[index] = ExtensionSection(s.name, s.bars + delta, s.active_roles, s.is_main)

    instr_idx = [i for i, s in enumerate(sections) if not s.is_main]
    cursor = 0
    while instr_idx and _seconds(sections) < 360.0:
        _bump(instr_idx[cursor % len(instr_idx)], loop_bars)
        cursor += 1
    while _seconds(sections) > 420.0:
        reducible = [i for i in instr_idx if sections[i].bars > loop_bars]
        if not reducible:
            break
        _bump(reducible[cursor % len(reducible)], -loop_bars)
        cursor += 1
    return ExtensionPlan(sections=sections, loop_bars=loop_bars, tempo_bpm=tempo_bpm)


def choose_loop_window(total_bars: int, loop_bars: int) -> int:
    """1-based start bar of a beat-aligned phrase from the steady middle."""
    if total_bars < loop_bars * 2:
        return 1
    centre = total_bars // 2
    start = centre - loop_bars // 2
    start = (start // loop_bars) * loop_bars + 1  # snap to a phrase boundary (1-based)
    start = max(loop_bars + 1, min(start, total_bars - loop_bars + 1))
    return start


def render_layout(plan: ExtensionPlan, spb: int) -> list[tuple[int, int, list[str], bool]]:
    layout: list[tuple[int, int, list[str], bool]] = []
    cursor = 0
    for section in plan.sections:
        length = section.bars * spb
        layout.append((cursor, cursor + length, section.active_roles, section.is_main))
        cursor += length
    return layout
