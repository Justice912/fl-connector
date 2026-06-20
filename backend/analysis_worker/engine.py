from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

Progress = Callable[[int, str, str], None]
MAX_AUDIO_SECONDS = 15 * 60


def infer_role(file_name: str, existing_role: str = "other") -> str:
    lowered = file_name.casefold()
    rules = [
        (("log drum", "log_drum"), "log_drum"),
        (("shaker", "perc", "conga", "bongo"), "percussion"),
        (("drum", "beat"), "drums"),
        (("bass", "sub"), "bass"),
        (("vocal", "vox", "voice"), "vocals"),
        (("piano", "keys", "chord", "pad"), "chords"),
        (("guitar",), "guitar"),
        (("melody", "lead", "pluck"), "melody"),
        (("fx", "effect", "ambience"), "fx"),
    ]
    for tokens, role in rules:
        if any(token in lowered for token in tokens):
            return role
    return existing_role if existing_role else "other"


def quantize_beats(value: float, grid: float = 0.25) -> float:
    return round(round(float(value) / grid) * grid, 4)


def classify_drum_hit(*, low: float, mid: float, high: float) -> int:
    largest = max((low, 36), (mid, 39), (high, 42), key=lambda item: item[0])
    return largest[1]


def validate_audio_duration(sample_count: int, sample_rate: int, file_name: str) -> None:
    if sample_rate <= 0:
        raise RuntimeError(f"Decoded sample rate is invalid: {file_name}")
    if sample_count / sample_rate > MAX_AUDIO_SECONDS:
        raise RuntimeError(f"Audio files may not exceed 15 minutes: {file_name}")


def analyze_project(project_path: Path, progress: Progress) -> dict[str, Any]:
    import json

    import librosa
    import numpy as np
    import pyloudnorm as pyln

    project_path = Path(project_path)
    project = json.loads((project_path / "project.json").read_text(encoding="utf-8"))
    stems = project.get("stems", [])
    if not stems:
        raise RuntimeError("project contains no stems")

    progress(5, "decode", "Decoding and aligning uploaded stems.")
    decoded: dict[str, tuple[Any, int, Any]] = {}
    duration = 0.0
    for index, stem in enumerate(stems):
        path = project_path / stem["relativePath"]
        multi, sample_rate = librosa.load(path, sr=22050, mono=False)
        mono = np.mean(multi, axis=0) if getattr(multi, "ndim", 1) > 1 else multi
        validate_audio_duration(len(mono), sample_rate, stem["fileName"])
        decoded[stem["id"]] = (mono, sample_rate, multi)
        duration = max(duration, len(mono) / sample_rate)
        progress(
            5 + int(15 * (index + 1) / len(stems)),
            "decode",
            f"Decoded {stem['fileName']}.",
        )

    reference = next(
        (
            stem
            for stem in stems
            if infer_role(stem["fileName"], stem.get("role", "other"))
            in {"drums", "percussion"}
        ),
        stems[0],
    )
    reference_audio, sample_rate, reference_multi = decoded[reference["id"]]
    onset_envelope = librosa.onset.onset_strength(y=reference_audio, sr=sample_rate)
    tempo_value, beat_frames = librosa.beat.beat_track(
        onset_envelope=onset_envelope,
        sr=sample_rate,
    )
    tempo = float(np.asarray(tempo_value).reshape(-1)[0])
    if not 40 <= tempo <= 240:
        tempo = 114.0
    bpm_confidence = min(0.98, 0.55 + len(beat_frames) / max(1, duration * 2))
    progress(28, "tempo", f"Detected {tempo:.2f} BPM.")

    key, scale, key_confidence = _detect_key(reference_audio, sample_rate, librosa, np)
    progress(38, "key", f"Detected {key} {scale}.")
    loudness, peak_db, stereo_width = _mix_measurements(
        reference_audio,
        reference_multi,
        sample_rate,
        np,
        pyln,
    )

    analyzed_stems = []
    for index, stem in enumerate(stems):
        role = infer_role(stem["fileName"], stem.get("role", "other"))
        audio, stem_rate, _multi = decoded[stem["id"]]
        warnings: list[str] = []
        if role in {"drums", "percussion"}:
            notes, confidence = _drum_notes(audio, stem_rate, tempo, librosa, np)
        elif role in {"vocals", "fx"}:
            notes, confidence = [], 0.95
        else:
            try:
                notes, confidence = _pitched_notes(
                    project_path / stem["relativePath"],
                    tempo,
                )
            except Exception as exc:
                notes, confidence = [], 0.55
                warnings.append(f"Pitch transcription failed: {exc}")
        analyzed_stems.append(
            {
                "stemId": stem["id"],
                "role": role,
                "confidence": round(confidence, 4),
                "notes": notes,
                "warnings": warnings,
            }
        )
        progress(
            40 + int(52 * (index + 1) / len(stems)),
            "transcription",
            f"Analyzed {stem['fileName']}.",
        )

    progress(96, "compile", "Writing analysis evidence for FL reconstruction.")
    return {
        "summary": {
            "bpm": round(tempo, 4),
            "bpmConfidence": round(bpm_confidence, 4),
            "key": key,
            "scale": scale,
            "keyConfidence": round(key_confidence, 4),
            "timeSignature": "4/4",
            "durationSeconds": round(duration, 4),
            "integratedLoudness": loudness,
            "peakDb": peak_db,
            "stereoWidth": stereo_width,
            "sections": [],
        },
        "stems": analyzed_stems,
    }


def _detect_key(audio, sample_rate, librosa, np):
    chroma = librosa.feature.chroma_cqt(y=audio, sr=sample_rate)
    profile = np.mean(chroma, axis=1)
    major = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    minor = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    candidates = []
    for root in range(12):
        candidates.append((float(np.corrcoef(profile, np.roll(major, root))[0, 1]), root, "major"))
        candidates.append((float(np.corrcoef(profile, np.roll(minor, root))[0, 1]), root, "minor"))
    score, root, scale = max(candidates, key=lambda item: item[0])
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    confidence = max(0.0, min(1.0, (score + 1) / 2))
    return names[root], scale, confidence


def _mix_measurements(mono, multi, sample_rate, np, pyln):
    peak = float(np.max(np.abs(mono))) if len(mono) else 0.0
    peak_db = round(20 * math.log10(max(peak, 1e-9)), 4)
    try:
        loudness = round(float(pyln.Meter(sample_rate).integrated_loudness(mono)), 4)
    except ValueError:
        loudness = None
    stereo_width = 0.0
    if getattr(multi, "ndim", 1) > 1 and multi.shape[0] >= 2:
        correlation = float(np.corrcoef(multi[0], multi[1])[0, 1])
        stereo_width = round(max(0.0, min(1.0, 1 - abs(correlation))), 4)
    return loudness, peak_db, stereo_width


def _drum_notes(audio, sample_rate, tempo, librosa, np):
    frames = librosa.onset.onset_detect(y=audio, sr=sample_rate, units="frames")
    spectrum = np.abs(librosa.stft(audio))
    frequencies = librosa.fft_frequencies(sr=sample_rate)
    notes = []
    for frame in frames:
        column = spectrum[:, min(int(frame), spectrum.shape[1] - 1)]
        low = float(np.sum(column[frequencies < 180]))
        mid = float(np.sum(column[(frequencies >= 180) & (frequencies < 2000)]))
        high = float(np.sum(column[frequencies >= 2000]))
        time_seconds = float(librosa.frames_to_time(frame, sr=sample_rate))
        notes.append(
            {
                "pitch": classify_drum_hit(low=low, mid=mid, high=high),
                "startBeats": quantize_beats(time_seconds * tempo / 60),
                "durationBeats": 0.125,
                "velocity": 0.78,
                "color": 2,
            }
        )
    confidence = min(0.95, 0.68 + len(notes) / 400)
    return notes, confidence


def _pitched_notes(path: Path, tempo: float):
    from basic_pitch.inference import predict

    _model_output, _midi_data, events = predict(str(path))
    notes = []
    amplitudes = []
    for event in events:
        start, end, pitch, amplitude = event[:4]
        amplitudes.append(float(amplitude))
        notes.append(
            {
                "pitch": int(round(pitch)),
                "startBeats": quantize_beats(float(start) * tempo / 60),
                "durationBeats": max(0.125, quantize_beats((float(end) - float(start)) * tempo / 60)),
                "velocity": max(0.1, min(1.0, float(amplitude))),
                "color": 7,
            }
        )
    average = sum(amplitudes) / len(amplitudes) if amplitudes else 0.0
    confidence = min(0.95, 0.58 + average * 0.35) if notes else 0.55
    return notes, confidence
