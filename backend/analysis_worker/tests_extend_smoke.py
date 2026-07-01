"""Worker-env smoke test. Run with: .analysis-worker/Scripts/python -m analysis_worker.tests_extend_smoke"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from analysis_worker.extend import extend_project


def _write_stem(folder: Path, name: str, seconds: float, sr: int = 44100) -> dict:
    n = int(seconds * sr)
    t = np.linspace(0, seconds, n, endpoint=False)
    tone = 0.2 * np.sin(2 * np.pi * 110 * t).astype("float32")
    (folder / "input").mkdir(parents=True, exist_ok=True)
    rel = f"input/{name}"
    sf.write(folder / rel, tone, sr)
    return {"id": name, "fileName": name, "relativePath": rel, "role": "other"}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        stems = [
            _write_stem(project, "drums.wav", 20.0),
            _write_stem(project, "bass.wav", 20.0),
            _write_stem(project, "vocals.wav", 12.0),
        ]
        (project / "project.json").write_text(json.dumps({"stems": stems}), encoding="utf-8")
        result = extend_project(project, {"genre": "amapiano", "targetSeconds": 390, "vocalMode": "place_once"},
                                lambda *a: None)
        wav = project / result["relativePath"]
        assert wav.exists(), "no wav written"
        info = sf.info(str(wav))
        assert 360 <= info.duration <= 420, f"duration {info.duration} out of window"
        print(f"OK smoke: {info.duration:.1f}s, warnings={result['warnings']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
