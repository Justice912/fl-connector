from __future__ import annotations

from .contracts import MasteringPlan, MixStep


def _step(
    order: int,
    target: str,
    plugin: str,
    slot: int,
    action: str,
    settings: dict[str, str],
    reason: str,
) -> MixStep:
    target_label = "Master" if target == "master" else target.replace("_", " ").title()
    return MixStep(
        order=order,
        target=target,
        plugin=plugin,
        slot=slot,
        action=action,
        settings=settings,
        clickPath=(
            f"Press F9 > select {target_label} mixer track > "
            f"effect slot {slot} > choose {plugin}"
        ),
        reason=reason,
    )


def generate_mastering_plan(
    *,
    prompt: str,
    genre: str = "Amapiano",
    bpm: int = 113,
) -> MasteringPlan:
    lowered = f"{prompt} {genre}".lower()
    is_deep = "deep" in lowered or "hypnotic" in lowered or "amapiano" in lowered
    target_loudness = "Club-ready, loud but not clipping; keep the master below -1 dB ceiling."

    steps = [
        _step(
            1,
            "drums",
            "Fruity Parametric EQ 2",
            1,
            "Clean sub rumble before compression.",
            {"Band 1": "High-pass around 30 Hz", "Band 4": "Small dip around 300 Hz if boxy"},
            "Keeps kick punch clear without low-end mud.",
        ),
        _step(
            2,
            "drums",
            "Fruity Compressor",
            2,
            "Light glue compression.",
            {"Ratio": "2:1", "Attack": "Medium", "Release": "Fast", "Gain reduction": "1-3 dB"},
            "Controls drum peaks while keeping bounce.",
        ),
        _step(
            3,
            "bass",
            "Fruity Parametric EQ 2",
            1,
            "Keep the bass focused below the melody.",
            {"Low end": "Keep 45-110 Hz strong", "Mud": "Cut a little around 200-350 Hz"},
            "Makes room for log drum and chords.",
        ),
        _step(
            4,
            "bass",
            "Fruity Stereo Shaper",
            2,
            "Keep sub bass mono.",
            {"Stereo": "Reduce width", "Low-end image": "Centered"},
            "Professional low-end should stay stable in mono playback.",
        ),
        _step(
            5,
            "chords",
            "Fruity Parametric EQ 2",
            1,
            "Remove low-end from pads/chords.",
            {"Band 1": "High-pass around 120 Hz", "Presence": "Gentle lift above 6 kHz if dull"},
            "Prevents pads from fighting bass and kick.",
        ),
        _step(
            6,
            "chords",
            "Fruity Reverb 2",
            2,
            "Add wide space without washing out the groove.",
            {"Wet": "Low to medium", "Decay": "2-4 seconds", "Low cut": "On"},
            "Deep Amapiano pads need space but not low-frequency reverb.",
        ),
        _step(
            7,
            "log_drum",
            "Fruity Parametric EQ 2",
            1,
            "Shape the log drum knock and remove harshness.",
            {"Body": "Gentle boost near 180-250 Hz", "Click": "Tiny lift near 2-4 kHz"},
            "Helps the log drum speak on small speakers.",
        ),
        _step(
            8,
            "log_drum",
            "Fruity Limiter",
            2,
            "Catch loud log drum hits.",
            {"Mode": "Limiter", "Ceiling": "-1 dB", "Gain": "Only if needed"},
            "Prevents the main melodic percussion from jumping out too hard.",
        ),
        _step(
            9,
            "melody",
            "Fruity Delay 3",
            1,
            "Create a subtle call-and-response echo.",
            {"Time": "1/4 or dotted 1/8", "Feedback": "Low", "Wet": "Low"},
            "Adds movement while leaving space for vocals or log drum.",
        ),
        _step(
            10,
            "master",
            "Fruity Parametric EQ 2",
            1,
            "Final tonal cleanup.",
            {"Sub": "High-pass around 25 Hz", "Mud": "Tiny cut around 250 Hz if needed", "Air": "Tiny shelf above 10 kHz"},
            "Small moves only; the master EQ should not repair a broken mix.",
        ),
        _step(
            11,
            "master",
            "Maximus",
            2,
            "Gentle multiband glue.",
            {"Preset": "Clear Master or Default", "Low band": "Light control", "High band": "Avoid harsh compression"},
            "Adds controlled loudness while keeping the groove natural.",
        ),
        _step(
            12,
            "master",
            "Fruity Limiter",
            3,
            "Set final ceiling and output safety.",
            {"Mode": "Limiter", "Ceiling": "-1 dB", "Gain": "Raise until loud, then back off if pumping"},
            "Final protection against clipping.",
        ),
    ]

    if is_deep:
        safety_notes = [
            "Route kick and bass to separate mixer tracks before mastering.",
            "Keep bass and kick centered; make pads and hats wider instead.",
            "If the master pumps, lower individual track volumes before raising limiter gain.",
            "Use built-in FL plugins only for this chain.",
        ]
    else:
        safety_notes = [
            "Balance track volumes before adding the master chain.",
            "Use limiter gain gently; loud but distorted is not professional.",
            "Use built-in FL plugins only for this chain.",
        ]

    return MasteringPlan.create(
        title=f"{genre} built-in mastering chain",
        sourcePrompt=prompt,
        genre=genre,
        bpm=bpm,
        targetLoudness=target_loudness,
        steps=steps,
        safetyNotes=safety_notes,
    )
