from __future__ import annotations

from .contracts import Note

_KNOWN_FAMILIES = {"amapiano", "afro", "hiphop"}

FILL_WINDOW_START = 3.0  # the fill occupies the last beat [3.0, 4.0) of a fill bar

# (pitch, offset_in_bar, durationBeats, velocity, color)
FillNote = tuple[int, float, float, float, int]

FILL_TEMPLATES: dict[str, tuple[FillNote, ...]] = {
    "amapiano": (
        (42, 3.0, 0.1, 0.50, 2),
        (42, 3.25, 0.1, 0.62, 2),
        (42, 3.5, 0.1, 0.74, 2),
        (42, 3.75, 0.1, 0.88, 2),
        (70, 3.0, 0.06, 0.30, 6),
        (70, 3.125, 0.06, 0.34, 6),
        (70, 3.25, 0.06, 0.39, 6),
        (70, 3.375, 0.06, 0.43, 6),
        (70, 3.5, 0.06, 0.48, 6),
        (70, 3.625, 0.06, 0.53, 6),
        (70, 3.75, 0.06, 0.57, 6),
        (70, 3.875, 0.06, 0.62, 6),
        # open hat sits on the 3.75 swing grid point, so the groove pass pushes it late;
        # its in-bar guarantee relies on the generator's post-groove boundary clamp.
        (46, 3.75, 0.18, 0.60, 4),
    ),
    "afro": (
        (36, 3.0, 0.18, 0.85, 5),
        (36, 3.5, 0.18, 0.80, 5),
        (39, 3.25, 0.14, 0.50, 3),
        (39, 3.75, 0.14, 0.82, 3),
        (42, 3.0, 0.1, 0.50, 2),
        (42, 3.25, 0.1, 0.50, 2),
        (42, 3.5, 0.1, 0.50, 2),
        (42, 3.75, 0.1, 0.50, 2),
    ),
    "hiphop": (
        (39, 3.0, 0.08, 0.40, 3),
        (39, 3.125, 0.08, 0.47, 3),
        (39, 3.25, 0.08, 0.54, 3),
        (39, 3.375, 0.08, 0.61, 3),
        (39, 3.5, 0.08, 0.69, 3),
        (39, 3.625, 0.08, 0.76, 3),
        (39, 3.75, 0.08, 0.83, 3),
        (39, 3.875, 0.08, 0.90, 3),
    ),
}


def _validate_tables() -> None:
    if set(FILL_TEMPLATES.keys()) != _KNOWN_FAMILIES:
        raise RuntimeError("FILL_TEMPLATES families are out of sync with the generator")
    for family, template in FILL_TEMPLATES.items():
        for _pitch, offset, duration, _velocity, _color in template:
            if not FILL_WINDOW_START <= offset < 4.0:
                raise RuntimeError(f"{family} fill offset {offset} is outside the fill window")
            if offset + duration > 4.0:
                raise RuntimeError(f"{family} fill note at offset {offset} exceeds the bar")


_validate_tables()


def _fill_bars(bars: int) -> set[int]:
    if bars <= 0:
        return set()
    fill_bars = {bar for bar in range(bars) if (bar + 1) % 4 == 0}
    fill_bars.add(bars - 1)
    return fill_bars


def apply_fills(notes: list[Note], *, family: str, bars: int) -> list[Note]:
    if not notes:
        return []
    if family not in FILL_TEMPLATES:
        raise ValueError(f"unknown fill family: {family}")
    template = FILL_TEMPLATES[family]
    fill_bars = _fill_bars(bars)
    result: list[Note] = []
    # 1) keep every base note except the last-beat hits of fill bars
    for note in notes:
        bar = int(note.startBeats // 4)
        window_start = bar * 4 + FILL_WINDOW_START
        window_end = bar * 4 + 4.0
        if bar in fill_bars and window_start <= note.startBeats < window_end:
            continue  # this steady hit gives way to the fill
        result.append(note)
    # 2) insert the genre fill on each fill bar's last beat
    for bar in sorted(fill_bars):
        base = bar * 4
        for pitch, offset, duration, velocity, color in template:
            result.append(Note(pitch, base + offset, duration, velocity, color))
    return result
