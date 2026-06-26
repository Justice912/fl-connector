from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, replace

from .contracts import Note

_KNOWN_FAMILIES = {"amapiano", "afro", "hiphop"}


@dataclass(frozen=True)
class GrooveTemplate:
    swing: float          # fraction of swing_grid that offbeats are pushed late (0..~0.5)
    swing_grid: float     # beats per subdivision whose offbeats swing (0.5 = 8th, 0.25 = 16th)
    timing_jitter: float  # max +/- beats of seeded micro-timing
    velocity_jitter: float  # max +/- velocity of seeded variation


GROOVE_TEMPLATES: dict[str, GrooveTemplate] = {
    "amapiano": GrooveTemplate(swing=0.32, swing_grid=0.25, timing_jitter=0.02, velocity_jitter=0.07),
    "afro": GrooveTemplate(swing=0.28, swing_grid=0.25, timing_jitter=0.02, velocity_jitter=0.07),
    "hiphop": GrooveTemplate(swing=0.18, swing_grid=0.5, timing_jitter=0.03, velocity_jitter=0.08),
}

# role -> (timing_mult, velocity_mult, swing_enabled)
ROLE_INTENSITY: dict[str, tuple[float, float, bool]] = {
    "drums": (1.0, 1.0, True),
    "log_drum": (1.0, 1.0, True),
    "melody": (1.0, 1.0, True),
    "bass": (0.6, 0.8, True),
    "chords": (0.0, 0.5, False),
    "_default": (0.6, 0.8, True),
}


def _validate_tables() -> None:
    if set(GROOVE_TEMPLATES.keys()) != _KNOWN_FAMILIES:
        raise RuntimeError("GROOVE_TEMPLATES families are out of sync with the generator")


_validate_tables()


def groove_seed(prompt: str, key: str, bars: int, genre: str, role: str) -> int:
    payload = "\x1f".join([prompt, key, str(bars), genre, role])
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def apply_groove(notes: list[Note], *, family: str, role: str, seed: int) -> list[Note]:
    template = GROOVE_TEMPLATES.get(family)
    if template is None:
        raise ValueError(f"unknown groove family: {family}")
    timing_mult, velocity_mult, swing_enabled = ROLE_INTENSITY.get(role, ROLE_INTENSITY["_default"])
    rng = random.Random(seed)
    grid = template.swing_grid
    result: list[Note] = []
    for note in notes:
        start = note.startBeats
        if swing_enabled and grid > 0 and abs((start % (2 * grid)) - grid) < 1e-6:
            start += template.swing * grid
        # Always advance the rng the same way per note (multiplier may be 0) so output stays deterministic.
        start += rng.uniform(-template.timing_jitter, template.timing_jitter) * timing_mult
        velocity = note.velocity + rng.uniform(-template.velocity_jitter, template.velocity_jitter) * velocity_mult
        start = round(max(0.0, start), 4)
        velocity = round(min(1.0, max(0.05, velocity)), 4)
        result.append(replace(note, startBeats=start, velocity=velocity))
    return result
