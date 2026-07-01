from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

Progress = Callable[[int, str, str], None]


def emit(progress: int, stage: str, message: str) -> None:
    print(json.dumps({"type": "progress", "progress": progress, "stage": stage, "message": message}), flush=True)


def _equal_power_fade(buffer, fade: int, np):
    """In-place equal-power fade-in at the start and fade-out at the end of a 1-D/2-D buffer."""
    n = buffer.shape[0]
    fade = int(min(fade, n // 2))
    if fade <= 0:
        return buffer
    curve = np.sqrt(np.linspace(0.0, 1.0, fade, dtype=buffer.dtype))
    shape = (fade,) + (1,) * (buffer.ndim - 1)
    buffer[:fade] *= curve.reshape(shape)
    buffer[n - fade:] *= curve[::-1].reshape(shape)
    return buffer


def _tile_into(dst, start: int, end: int, loop, fade: int, np) -> None:
    """Fill dst[start:end] by repeating `loop`, with an equal-power fade at the span edges."""
    length = end - start
    if length <= 0 or loop.shape[0] == 0:
        return
    reps = length // loop.shape[0] + 1
    tiled = np.tile(loop, (reps,) + (1,) * (loop.ndim - 1))[:length]
    _equal_power_fade(tiled, fade, np)
    dst[start:end] += tiled


def extend_project(project_path: Path, options: dict[str, Any], progress: Progress) -> dict[str, Any]:
    import librosa
    import numpy as np
    import soundfile as sf

    from app.extension_plan import build_extension_plan, choose_loop_window, render_layout, samples_per_bar
    from analysis_worker.engine import infer_role

    project = json.loads((project_path / "project.json").read_text(encoding="utf-8"))
    stems = project.get("stems", [])
    if not stems:
        raise RuntimeError("project contains no stems")

    sr = 44100
    progress(5, "decode", "Loading stems.")
    decoded: list[tuple[str, Any]] = []  # (role, audio[n, channels])
    vocal_audio = None
    duration = 0.0
    for index, stem in enumerate(stems):
        y, _ = librosa.load(project_path / stem["relativePath"], sr=sr, mono=False)
        audio = np.atleast_2d(y).T if y.ndim == 1 else y.T  # -> shape (n, channels)
        role = infer_role(stem["fileName"], stem.get("role", "other"))
        decoded.append((role, audio.astype(np.float32)))
        duration = max(duration, audio.shape[0] / sr)
        if role == "vocals":
            vocal_audio = audio.astype(np.float32)
        progress(5 + int(15 * (index + 1) / len(stems)), "decode", f"Loaded {stem['fileName']}.")

    channels = max(int(a.shape[1]) for _role, a in decoded)

    def _fit_channels(a):
        if int(a.shape[1]) == channels:
            return a
        return np.repeat(a[:, :1], channels, axis=1)

    decoded = [(role, _fit_channels(a)) for role, a in decoded]
    if vocal_audio is not None:
        vocal_audio = _fit_channels(vocal_audio)

    # Light tempo detection from the busiest stem.
    ref = max(decoded, key=lambda item: float(np.mean(np.abs(item[1]))))[1].mean(axis=1)
    tempo_value, _beats = librosa.beat.beat_track(y=ref, sr=sr)
    tempo = float(np.asarray(tempo_value).reshape(-1)[0])
    if not 60 <= tempo <= 200:
        tempo = 112.0
    progress(28, "tempo", f"Detected {tempo:.1f} BPM.")

    spb = samples_per_bar(tempo, sr)
    source_bars = max(1, int(duration * sr) // spb)
    loop_bars = 16 if source_bars >= 32 else 8
    roles = sorted({role for role, _ in decoded})
    vocal_seconds = float(vocal_audio.shape[0] / sr) if vocal_audio is not None else None
    plan = build_extension_plan(genre=str(options.get("genre", "amapiano")), tempo_bpm=tempo,
                                loop_bars=loop_bars, target_seconds=float(options.get("targetSeconds", 390.0)),
                                roles=roles, vocal_seconds=vocal_seconds)
    layout = render_layout(plan, spb)
    total = plan.total_bars() * spb
    loop_start = (choose_loop_window(source_bars, loop_bars) - 1) * spb
    fade = int(0.010 * sr)  # 10 ms
    vocal_mode = str(options.get("vocalMode", "place_once"))
    warnings: list[str] = []

    progress(40, "render", "Arranging sections.")
    mix = np.zeros((total, channels), dtype=np.float32)
    for role, audio in decoded:
        if role == "vocals" and vocal_mode == "drop":
            continue
        loop = audio[loop_start:loop_start + loop_bars * spb]
        if loop.shape[0] < loop_bars * spb:
            loop = audio[: loop_bars * spb]
            warnings.append("Stem shorter than the loop phrase; used its start.")
        buf = np.zeros((total, channels), dtype=np.float32)
        if role == "vocals" and vocal_mode == "place_once":
            main_spans = [(s0, e0) for (s0, e0, _roles, is_main) in layout if is_main]
            if main_spans and vocal_audio is not None:
                start = main_spans[0][0]
                clip = vocal_audio[: total - start]
                seg = buf[start:start + clip.shape[0]]
                seg += clip[: seg.shape[0]]
                _equal_power_fade(buf[start:start + clip.shape[0]], fade, np)
        else:
            for (s0, e0, active, _is_main) in layout:
                if role in active:
                    _tile_into(buf, s0, e0, loop, fade, np)
        mix += buf
        progress(min(90, 40 + int(45 * (len(warnings) + 1) / max(1, len(decoded)))), "render", f"Placed {role}.")

    peak = float(np.max(np.abs(mix))) or 1.0
    mix = (mix / peak) * 0.98

    out_dir = project_path / "extended"
    out_dir.mkdir(parents=True, exist_ok=True)
    sf.write(out_dir / "extended-mix.wav", mix, sr)
    progress(97, "write", "Wrote extended mix.")
    return {"relativePath": "extended/extended-mix.wav",
            "durationSeconds": round(total / sr, 3),
            "warnings": sorted(set(warnings))}


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an extended mix from reconstruction stems.")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--options", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        options = json.loads(args.options.read_text(encoding="utf-8"))
        result = extend_project(args.project, options, emit)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        emit(100, "complete", "Extended mix result written.")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
