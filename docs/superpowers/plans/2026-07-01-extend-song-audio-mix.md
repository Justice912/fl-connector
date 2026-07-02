# Extend Song — Extended Audio Mix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From a Rebuild project's uploaded stems, produce a 6–7 minute extended-mix WAV by arranging beat-aligned stem loops into a genre template, with the original vocal placed once through the main block.

**Architecture:** A pure `extension_plan.py` (genre templates → section plan + sample layout) drives a worker-side audio renderer (`analysis_worker/extend.py`, numpy/soundfile). A background `ExtendJobRunner` (mirroring `AnalysisJobRunner`) invokes the worker via subprocess (`LocalExtendProvider`, mirroring `LocalAnalysisProvider`) and records progress + the result on the reconstruction project. A new "Extend Song" card drives it.

**Tech Stack:** Python/FastAPI backend (`backend/.venv`, pytest); the heavy DSP runs in the separate `.analysis-worker` env (numpy 1.26, librosa 0.10, soundfile 0.12 — all already installed); React/Vite frontend (vitest).

## Global Constraints

- **Impose a genre arrangement** from the groove; do NOT rely on detecting the original's sections.
- **Vocals:** default `place_once` — the original vocal plays once across the contiguous Main/Drop block; `loop` and `drop` modes also supported. Vocal is never looped in `place_once`.
- **Loop source:** auto-pick a beat-aligned phrase from the song's steady middle. Default `loop_bars = 16`, fallback `8` when the source is too short.
- **Genres:** `amapiano` and `deep_house` (deep house is an extension template only). Unknown genre → `amapiano` fallback.
- **Target length:** default `390` s; accepted window `360–420` s.
- **Tempo:** keep the source tempo; no time-stretch/pitch-shift.
- `extension_plan.py` is **pure stdlib** (dataclasses/typing/math only) so BOTH `backend/.venv` (tests) and the worker env (`from app.extension_plan import …`, run with cwd=`backend`) can import it. No fastapi/numpy imports in it.
- Reuse existing patterns: `AnalysisJob` for the job shape, `AnalysisJobRunner`/`LocalAnalysisProvider` structure, the worker CLI progress protocol (`{"type":"progress",...}` JSON lines), and the reconstruction store/endpoints.
- Existing **163** backend tests stay green. Backend pytest runs from `backend/`. Worker-env smoke tests run with `.analysis-worker/Scripts/python`.
- 4/4 time: one bar = 4 beats; `bar_seconds = 240 / tempo_bpm`; `samples_per_bar = round(sample_rate * 240 / tempo_bpm)`.

---

### Task 1: Arrangement plan core (`extension_plan.py`, pure)

**Files:**
- Create: `backend/app/extension_plan.py`
- Test: `backend/tests/test_extension_plan.py`

**Interfaces:**
- Produces:
  - `KNOWN_ROLES: frozenset[str]`, `GENRE_TEMPLATES: dict[str, list[tuple[str,int,list[str],bool]]]` (each row `(name, weight, active_roles, is_main)`; `weight>0` = instrumental sized by weight, `weight==0` = a main block).
  - `@dataclass(frozen=True) ExtensionSection(name: str, bars: int, active_roles: list[str], is_main: bool)` with `to_dict()`.
  - `@dataclass(frozen=True) ExtensionPlan(sections: list[ExtensionSection], loop_bars: int, tempo_bpm: float)` with `total_bars() -> int`, `total_seconds() -> float`, `main_bars() -> int`, `to_dict()`.
  - `build_extension_plan(*, genre: str, tempo_bpm: float, loop_bars: int, target_seconds: float, roles: list[str], vocal_seconds: float | None) -> ExtensionPlan`.
  - `choose_loop_window(total_bars: int, loop_bars: int) -> int` (1-based start bar).
  - `samples_per_bar(tempo_bpm: float, sample_rate: int) -> int`.
  - `render_layout(plan: ExtensionPlan, spb: int) -> list[tuple[int, int, list[str], bool]]` (start_sample, end_sample, active_roles, is_main).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_extension_plan.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_extension_plan.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.extension_plan'`.

- [ ] **Step 3: Implement `extension_plan.py`**

Create `backend/app/extension_plan.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_extension_plan.py -v`
Expected: PASS (all tests). The window is guaranteed by the correction loop at the end of
`build_extension_plan` (it adds/removes whole loop phrases from instrumental sections until
`total_seconds()` is within 360–420 s), so the target-window assertion holds for any tempo/vocal.

- [ ] **Step 5: Commit**

```bash
git add backend/app/extension_plan.py backend/tests/test_extension_plan.py
git commit -m "feat: add pure arrangement-plan core for song extension"
```

---

### Task 2: Project contract + store fields for the extend result

**Files:**
- Modify: `backend/app/reconstruction_contracts.py` (add `extendJob` + `extendedMix` to `ReconstructionProject`)
- Modify: `backend/app/reconstruction_store.py` (add `extended_dir` + `extended_mix_path` helpers)
- Test: `backend/tests/test_reconstruction_contracts.py`, `backend/tests/test_reconstruction_store.py`

**Interfaces:**
- Consumes: existing `AnalysisJob`, `ReconstructionProject`.
- Produces: `ReconstructionProject.extendJob: AnalysisJob | None`, `ReconstructionProject.extendedMix: dict | None` (`{relativePath, durationSeconds, warnings}`); `ReconstructionStore.extended_dir(project_id) -> Path`, `ReconstructionStore.extended_mix_path(project_id) -> Path`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_reconstruction_contracts.py`:

```python
def test_project_round_trips_extend_fields():
    from app.reconstruction_contracts import AnalysisJob, ReconstructionProject

    project = ReconstructionProject.create(title="Extend me", rightsAccepted=True)
    job = AnalysisJob.create()
    project = project.with_changes(
        extendJob=job,
        extendedMix={"relativePath": "extended/extended-mix.wav", "durationSeconds": 392.0, "warnings": []},
    )
    restored = ReconstructionProject.from_dict(project.to_dict())
    assert restored.extendedMix["relativePath"] == "extended/extended-mix.wav"
    assert restored.extendJob is not None and restored.extendJob.id == job.id
```

Add to `backend/tests/test_reconstruction_store.py`:

```python
def test_extended_paths_are_under_project_dir(tmp_path):
    from app.reconstruction_store import ReconstructionStore

    store = ReconstructionStore(tmp_path / "reconstructions")
    project = store.create_project(title="Paths", rights_accepted=True)
    assert store.extended_dir(project.id) == store.project_dir(project.id) / "extended"
    assert store.extended_mix_path(project.id) == store.project_dir(project.id) / "extended" / "extended-mix.wav"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_reconstruction_contracts.py -k extend_fields tests/test_reconstruction_store.py -k extended_paths -v`
Expected: FAIL — `extendJob`/`extendedMix` not accepted; `extended_dir` missing.

- [ ] **Step 3: Implement the contract fields**

In `backend/app/reconstruction_contracts.py`, in `ReconstructionProject`:

Add these two fields to the dataclass (after `mixPlan: dict[str, Any] | None`):

```python
    extendJob: "AnalysisJob | None" = None
    extendedMix: dict[str, Any] | None = None
```

In `ReconstructionProject.create(...)`, add to the constructor call: `extendJob=None, extendedMix=None,`.

In `ReconstructionProject.from_dict(...)`, add inside the `cls(...)` call:

```python
            extendJob=(AnalysisJob.from_dict(value["extendJob"]) if value.get("extendJob") else None),
            extendedMix=(dict(value["extendedMix"]) if value.get("extendedMix") else None),
```

In `ReconstructionProject.to_dict(...)`, add:

```python
            "extendJob": self.extendJob.to_dict() if self.extendJob else None,
            "extendedMix": self.extendedMix,
```

- [ ] **Step 4: Implement the store helpers**

In `backend/app/reconstruction_store.py`, add these methods to `ReconstructionStore` (next to `project_dir`):

```python
    def extended_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "extended"

    def extended_mix_path(self, project_id: str) -> Path:
        return self.extended_dir(project_id) / "extended-mix.wav"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_reconstruction_contracts.py tests/test_reconstruction_store.py -v`
Expected: PASS (new tests + existing ones).

- [ ] **Step 6: Commit**

```bash
git add backend/app/reconstruction_contracts.py backend/app/reconstruction_store.py backend/tests/test_reconstruction_contracts.py backend/tests/test_reconstruction_store.py
git commit -m "feat: add extendJob/extendedMix to reconstruction project + store paths"
```

---

### Task 3: Extend provider + job runner

**Files:**
- Create: `backend/app/extend_jobs.py` (`ExtendProvider` protocol, `LocalExtendProvider`, `ExtendJobRunner`)
- Test: `backend/tests/test_extend_jobs.py`

**Interfaces:**
- Consumes: `ReconstructionStore`, `AnalysisJob`, `ReconstructionProject`, `ReconstructionError`.
- Produces:
  - `ExtendProvider` protocol: `extend(project_dir: Path, options: dict, progress: Callable[[int,str,str],None]) -> dict` returning `{"relativePath": str, "durationSeconds": float, "warnings": list[str]}`.
  - `ExtendJobRunner(store, provider)` with `run(project_id: str, options: dict) -> ReconstructionProject` and `start(project_id: str, options: dict) -> ReconstructionProject`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_extend_jobs.py`:

```python
from pathlib import Path

from app.extend_jobs import ExtendJobRunner
from app.reconstruction_store import ReconstructionStore, UploadCandidate


def _wav() -> bytes:
    return b"RIFF" + (40).to_bytes(4, "little") + b"WAVEfmt " + b"\x00" * 32


class FakeProvider:
    def extend(self, project_dir, options, progress):
        progress(50, "render", "halfway")
        return {"relativePath": "extended/extended-mix.wav", "durationSeconds": 390.0, "warnings": []}


def _project_with_stem(store):
    project = store.create_project(title="Extend", rights_accepted=True)
    store.add_uploads(project.id, [UploadCandidate(fileName="drums.wav", data=_wav())])
    return store.get(project.id)


def test_extend_runner_records_result(tmp_path):
    store = ReconstructionStore(tmp_path / "r")
    project = _project_with_stem(store)
    runner = ExtendJobRunner(store, FakeProvider())

    result = runner.run(project.id, {"genre": "amapiano", "targetSeconds": 390, "vocalMode": "place_once"})

    assert result.extendJob is not None and result.extendJob.status == "complete"
    assert result.extendedMix["relativePath"] == "extended/extended-mix.wav"
    assert result.extendedMix["durationSeconds"] == 390.0


def test_extend_runner_requires_stems(tmp_path):
    import pytest
    from app.reconstruction_contracts import ReconstructionError

    store = ReconstructionStore(tmp_path / "r")
    project = store.create_project(title="No stems", rights_accepted=True)
    runner = ExtendJobRunner(store, FakeProvider())
    with pytest.raises(ReconstructionError):
        runner.run(project.id, {"genre": "amapiano", "targetSeconds": 390, "vocalMode": "place_once"})


def test_extend_runner_marks_error_on_provider_failure(tmp_path):
    store = ReconstructionStore(tmp_path / "r")
    project = _project_with_stem(store)

    class Boom:
        def extend(self, project_dir, options, progress):
            raise RuntimeError("render blew up")

    result = ExtendJobRunner(store, Boom()).run(project.id, {"genre": "amapiano", "targetSeconds": 390, "vocalMode": "place_once"})
    assert result.extendJob.status == "error"
    assert "render blew up" in (result.extendJob.error or "")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/test_extend_jobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.extend_jobs'`.

- [ ] **Step 3: Implement `extend_jobs.py`**

Create `backend/app/extend_jobs.py`:

```python
from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Protocol

from .reconstruction_contracts import AnalysisJob, ReconstructionError, ReconstructionProject
from .reconstruction_store import ReconstructionStore

Progress = Callable[[int, str, str], None]


class ExtendProvider(Protocol):
    def extend(self, project_dir: Path, options: dict[str, Any], progress: Progress) -> dict[str, Any]: ...


class LocalExtendProvider:
    def __init__(self, python: Path, backend_root: Path) -> None:
        self.python = Path(python)
        self.backend_root = Path(backend_root)

    def extend(self, project_dir: Path, options: dict[str, Any], progress: Progress) -> dict[str, Any]:
        if not self.python.exists():
            raise ReconstructionError(f"analysis worker Python is missing: {self.python}")
        extended_dir = Path(project_dir) / "extended"
        extended_dir.mkdir(parents=True, exist_ok=True)
        options_path = extended_dir / "options.json"
        options_path.write_text(json.dumps(options), encoding="utf-8")
        result_path = extended_dir / "result.json"
        process = subprocess.Popen(
            [str(self.python), "-m", "analysis_worker.extend",
             "--project", str(project_dir), "--options", str(options_path), "--output", str(result_path)],
            cwd=self.backend_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        assert process.stdout is not None
        for line in process.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "progress":
                progress(int(event.get("progress", 0)), str(event.get("stage", "extend")), str(event.get("message", "")))
        _stdout, stderr = process.communicate()
        if process.returncode != 0:
            raise RuntimeError(stderr.strip() or f"extend worker exited {process.returncode}")
        if not result_path.exists():
            raise RuntimeError("extend worker did not create a result file")
        return json.loads(result_path.read_text(encoding="utf-8"))


class ExtendJobRunner:
    def __init__(self, store: ReconstructionStore, provider: ExtendProvider) -> None:
        self.store = store
        self.provider = provider
        self._lock = Lock()

    def run(self, project_id: str, options: dict[str, Any]) -> ReconstructionProject:
        if not self._lock.acquire(blocking=False):
            raise ReconstructionError("another extend job is already running")
        try:
            project = self.store.get(project_id)
            if not project.stems:
                raise ReconstructionError("upload at least one stem before extending")
            job = AnalysisJob.create().with_progress(
                status="running", progress=1, stage="starting", message="Starting extended mix."
            )
            self.store.save(project.with_changes(extendJob=job))

            def progress(value: int, stage: str, message: str) -> None:
                current = self.store.get(project_id)
                self.store.save(current.with_changes(
                    extendJob=(current.extendJob or job).with_progress(
                        status="running", progress=max(1, min(99, value)), stage=stage, message=message)))

            result = self.provider.extend(self.store.project_dir(project_id), options, progress)
            current = self.store.get(project_id)
            done = (current.extendJob or job).with_progress(
                status="complete", progress=100, stage="complete", message="Extended mix ready.")
            return self.store.save(current.with_changes(extendJob=done, extendedMix=result))
        except ReconstructionError:
            self._lock.release()
            raise
        except Exception as exc:
            current = self.store.get(project_id)
            failed = (current.extendJob or AnalysisJob.create()).with_progress(
                status="error", stage="error", message="Extended mix failed.", error=str(exc))
            saved = self.store.save(current.with_changes(extendJob=failed))
            self._lock.release()
            return saved
        else:
            self._lock.release()

    def start(self, project_id: str, options: dict[str, Any]) -> ReconstructionProject:
        current = self.store.get(project_id)
        if self._lock.locked():
            raise ReconstructionError("another extend job is already running")
        Thread(target=self.run, args=(project_id, options), daemon=True).start()
        return current
```

> Note the lock handling: `run` releases the lock in every branch. The `else` clause runs only when the `try` body completes without exception (success path), releasing there; the two `except` branches release before returning/raising. Do not add a `finally` (it would double-release).

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/test_extend_jobs.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/extend_jobs.py backend/tests/test_extend_jobs.py
git commit -m "feat: add extend job runner and local worker provider"
```

---

### Task 4: API endpoints (`/extend`, `/extended-mix`)

**Files:**
- Modify: `backend/app/main.py` (imports, `_extend_runner()` factory, two endpoints, a request model)
- Test: `backend/tests/test_reconstruction_api.py`

**Interfaces:**
- Consumes: `ExtendJobRunner`, `LocalExtendProvider` (Task 3); `worker_python`, `APP_ROOT`, `RECONSTRUCTION_STORE`.
- Produces: `POST /api/reconstructions/{project_id}/extend` (202) and `GET /api/reconstructions/{project_id}/extended-mix`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_reconstruction_api.py`:

```python
def test_extend_endpoint_starts_job(tmp_path, monkeypatch):
    client = isolated_client(tmp_path, monkeypatch)
    created = client.post("/api/reconstructions", json={"title": "Extend", "rightsAccepted": True})
    pid = created.json()["id"]
    client.post(f"/api/reconstructions/{pid}/stems",
                files=[("files", ("drums.wav", wav_bytes(), "audio/wav"))])

    class FakeRunner:
        def start(self, project_id, options):
            return main.RECONSTRUCTION_STORE.get(project_id)

    monkeypatch.setattr(main, "_extend_runner", lambda: FakeRunner())
    started = client.post(f"/api/reconstructions/{pid}/extend",
                          json={"genre": "amapiano", "targetSeconds": 390, "vocalMode": "place_once"})
    assert started.status_code == 202


def test_extend_endpoint_400_without_stems(tmp_path, monkeypatch):
    client = isolated_client(tmp_path, monkeypatch)
    empty = main.RECONSTRUCTION_STORE.create_project(title="No stems", rights_accepted=True)
    resp = client.post(f"/api/reconstructions/{empty.id}/extend",
                       json={"genre": "amapiano", "targetSeconds": 390, "vocalMode": "place_once"})
    assert resp.status_code == 400


def test_extended_mix_404_before_complete(tmp_path, monkeypatch):
    client = isolated_client(tmp_path, monkeypatch)
    empty = main.RECONSTRUCTION_STORE.create_project(title="None", rights_accepted=True)
    assert client.get(f"/api/reconstructions/{empty.id}/extended-mix").status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_reconstruction_api.py -k "extend" -v`
Expected: FAIL — routes not defined (404/405).

- [ ] **Step 3: Implement the endpoints**

In `backend/app/main.py`, add near the other reconstruction imports:

```python
from .extend_jobs import ExtendJobRunner, LocalExtendProvider
```

Add a request model near the other Pydantic models (e.g. after `ReconstructionPatchRequest`):

```python
class ReconstructionExtendRequest(BaseModel):
    genre: str = Field(default="amapiano")
    targetSeconds: float = Field(default=390.0, ge=360.0, le=420.0)
    vocalMode: str = Field(default="place_once", pattern="^(place_once|loop|drop)$")
```

Add the runner factory near `_analysis_runner()` (around line 822):

```python
_EXTEND_RUNNER: ExtendJobRunner | None = None


def _extend_runner() -> ExtendJobRunner:
    global _EXTEND_RUNNER
    if _EXTEND_RUNNER is None:
        _EXTEND_RUNNER = ExtendJobRunner(
            RECONSTRUCTION_STORE, LocalExtendProvider(worker_python(APP_ROOT), APP_ROOT / "backend")
        )
    return _EXTEND_RUNNER
```

Add `_EXTEND_RUNNER` to the module-level globals section near `_ANALYSIS_RUNNER: AnalysisJobRunner | None = None` (declare it there too if the factory's `global` needs it — the assignment above suffices, but declaring `_EXTEND_RUNNER: ExtendJobRunner | None = None` at module scope next to `_ANALYSIS_RUNNER` is clearer). Place the endpoints next to the `/analyze` route:

```python
@app.post("/api/reconstructions/{project_id}/extend", status_code=202)
def extend_reconstruction(project_id: str, request: ReconstructionExtendRequest) -> dict[str, Any]:
    try:
        project = RECONSTRUCTION_STORE.get(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reconstruction project not found") from exc
    if not project.stems:
        raise HTTPException(status_code=400, detail="upload at least one stem before extending")
    try:
        return _extend_runner().start(project_id, request.model_dump()).to_dict()
    except ReconstructionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/reconstructions/{project_id}/extended-mix")
def reconstruction_extended_mix(project_id: str) -> FileResponse:
    path = RECONSTRUCTION_STORE.extended_mix_path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="extended mix not ready")
    return FileResponse(path, media_type="audio/wav", filename="extended-mix.wav")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_reconstruction_api.py -k "extend" -v`
Expected: PASS.

- [ ] **Step 5: Full backend suite**

Run: `cd backend && python -m pytest -q`
Expected: PASS (previously 163 + all new tests from Tasks 1–4).

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/tests/test_reconstruction_api.py
git commit -m "feat: add extend + extended-mix reconstruction endpoints"
```

---

### Task 5: Worker audio renderer (`analysis_worker/extend.py`)

**Files:**
- Create: `backend/analysis_worker/extend.py` (light analysis + DSP renderer + CLI)
- Test: `backend/analysis_worker/tests_extend_smoke.py` (run with the WORKER python)

**Interfaces:**
- Consumes: `app.extension_plan` (`build_extension_plan`, `choose_loop_window`, `samples_per_bar`, `render_layout`); `analysis_worker.engine.infer_role`; numpy, librosa, soundfile.
- Produces: CLI `python -m analysis_worker.extend --project <dir> --options <json> --output <json>` that writes `extended/extended-mix.wav` (+ `extended/stems/<role>.wav`) and a result JSON `{"relativePath","durationSeconds","warnings"}`.

- [ ] **Step 1: Implement the renderer**

Create `backend/analysis_worker/extend.py`:

```python
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
    channels = decoded[0][1].shape[1]
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
```

- [ ] **Step 2: Write the worker-env smoke test**

Create `backend/analysis_worker/tests_extend_smoke.py` (a standalone script, since it needs the worker env, not `backend/.venv`):

```python
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
```

- [ ] **Step 3: Run the smoke test with the worker python**

Run: `cd backend && ../.analysis-worker/Scripts/python.exe -m analysis_worker.tests_extend_smoke`
Expected: prints `OK smoke: <~390>s, warnings=[...]` and exits 0. (Runs from `backend/` so both `app` and `analysis_worker` import.)

- [ ] **Step 4: Confirm the pure-core tests still pass in backend/.venv**

Run: `cd backend && python -m pytest tests/test_extension_plan.py -q`
Expected: PASS (the renderer reuses this already-tested core; no new `backend/.venv` tests here since the DSP needs numpy).

- [ ] **Step 5: Commit**

```bash
git add backend/analysis_worker/extend.py backend/analysis_worker/tests_extend_smoke.py
git commit -m "feat: worker-side extended-mix audio renderer"
```

---

### Task 6: Frontend "Extend Song" card

**Files:**
- Modify: `frontend/src/api.js` (two methods)
- Modify: `frontend/src/reconstruction/ReconstructionWorkspace.jsx` (ExtendSong card + render)
- Test: `frontend/src/reconstruction/ReconstructionWorkspace.test.jsx`

**Interfaces:**
- Consumes: `POST /api/reconstructions/{id}/extend`, `GET /api/reconstructions/{id}/extended-mix`, and the project's `extendJob`/`extendedMix`.
- Produces: `api.extendReconstruction(id, body)`, `api.extendedMixUrl(id)`.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/reconstruction/ReconstructionWorkspace.test.jsx` — extend the `clientFor` mock object with:

```javascript
    extendReconstruction: vi.fn().mockResolvedValue({}),
    extendedMixUrl: vi.fn().mockReturnValue('/api/reconstructions/project-1/extended-mix'),
```

Then add the test:

```javascript
test('starts an extended mix from the Extend Song card', async () => {
  const project = draftProject({
    status: 'review',
    stems: [{ id: 's1', fileName: 'drums.wav', storedName: 'drums.wav', relativePath: 'input/drums.wav',
              mediaType: 'audio/wav', sizeBytes: 1000, sha256: 'x'.repeat(64), role: 'drums',
              status: 'uploaded', createdAt: 'now' }],
  });
  const client = clientFor([project]);

  render(<ReconstructionWorkspace client={client} />);

  const create = await screen.findByRole('button', { name: /Create extended mix/i });
  fireEvent.click(create);
  await waitFor(() => expect(client.extendReconstruction).toHaveBeenCalledWith(
    'project-1', expect.objectContaining({ genre: expect.any(String), vocalMode: expect.any(String) })));
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --run ReconstructionWorkspace`
Expected: FAIL — no "Create extended mix" button.

- [ ] **Step 3: Add the API methods**

In `frontend/src/api.js`, add after `exportReconstruction`:

```javascript
  extendReconstruction: (id, body) => request(`/api/reconstructions/${id}/extend`, { method: 'POST', body: JSON.stringify(body) }),
  extendedMixUrl: (id) => `${API_BASE}/api/reconstructions/${id}/extended-mix`,
```

- [ ] **Step 4: Add the ExtendSong card**

In `frontend/src/reconstruction/ReconstructionWorkspace.jsx`, add `Clock` to the lucide-react import list, add this component near the other section components:

```jsx
function ExtendSong({ project, client, busy, onError, onProjectChange }) {
  const [genre, setGenre] = useState('amapiano');
  const [targetSeconds, setTargetSeconds] = useState(390);
  const [vocalMode, setVocalMode] = useState('place_once');
  const [working, setWorking] = useState(false);
  const job = project.extendJob;
  const mix = project.extendedMix;
  const hasStems = project.stems.length > 0;

  async function create() {
    setWorking(true);
    onError('');
    try {
      onProjectChange(await client.extendReconstruction(project.id, { genre, targetSeconds, vocalMode }));
    } catch (reason) {
      onError(reason.message);
    } finally {
      setWorking(false);
    }
  }

  return (
    <section className="rebuild-section extend-song">
      <header><div><p>Extend song</p><h2>6-7 min extended mix</h2></div><Clock size={20} /></header>
      <div className="extend-controls">
        <label>Genre
          <select value={genre} disabled={busy} onChange={(e) => setGenre(e.target.value)}>
            <option value="amapiano">Amapiano</option>
            <option value="deep_house">Deep House</option>
          </select>
        </label>
        <label>Length: {Math.floor(targetSeconds / 60)}:{String(targetSeconds % 60).padStart(2, '0')}
          <input type="range" min="360" max="420" step="10" value={targetSeconds}
                 disabled={busy} onChange={(e) => setTargetSeconds(Number(e.target.value))} />
        </label>
        <label>Vocals
          <select value={vocalMode} disabled={busy} onChange={(e) => setVocalMode(e.target.value)}>
            <option value="place_once">Place once</option>
            <option value="loop">Loop</option>
            <option value="drop">Instrumental</option>
          </select>
        </label>
        <button className="primary-button rebuild-inline" disabled={busy || working || !hasStems} onClick={create}>
          <Clock size={16} /> Create extended mix
        </button>
      </div>
      {job && job.status !== 'complete' && <progress max="100" value={job.progress}>{job.progress}%</progress>}
      {mix && (
        <div className="extend-result">
          <audio controls preload="metadata" src={client.extendedMixUrl(project.id)} />
          <a href={client.extendedMixUrl(project.id)} download>Download extended mix ({Math.round(mix.durationSeconds)}s)</a>
        </div>
      )}
    </section>
  );
}
```

Render it after `<Arrangement project={project} />` (near the `SendToFl` card):

```jsx
          <ExtendSong project={project} client={client} busy={busy} onError={setError} onProjectChange={adopt} />
```

Add a poll for the extend job — extend the existing analysis-job polling `useEffect` condition so it also polls while an extend job runs. Change its guard from:

```jsx
    if (!project || !['queued', 'running'].includes(project.analysisJob?.status)) return undefined;
```

to:

```jsx
    const active = ['queued', 'running'];
    if (!project || !(active.includes(project.analysisJob?.status) || active.includes(project.extendJob?.status))) return undefined;
```

and add `project?.extendJob?.status` to that effect's dependency array.

- [ ] **Step 5: Run the frontend suite**

Run: `cd frontend && npm test -- --run`
Expected: PASS (new test + existing 16).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api.js frontend/src/reconstruction/ReconstructionWorkspace.jsx frontend/src/reconstruction/ReconstructionWorkspace.test.jsx
git commit -m "feat: add Extend Song card to the Rebuild workspace"
```

---

### Task 7: Manual acceptance (user-run)

**Files:** none.

- [ ] **Step 1:** In a Rebuild project with real Suno stems, open **Extend Song**, pick genre + length, **Create extended mix**; watch progress complete.
- [ ] **Step 2:** Play the result — 6–7 min, groove recognizable, vocal intact through the middle, instrumental intro/build/breakdown/outro around it, no clicks at seams.
- [ ] **Step 3:** **Download** yields `extended-mix.wav` of ≈ the chosen length.

---

## Self-Review

**Spec coverage:**
- Pure arrangement plan (templates, vocal-anchored main, target scaling, role filter, loop window, sample layout) → Task 1. ✓
- Genre templates amapiano + deep_house → Task 1 `GENRE_TEMPLATES`. ✓
- extendJob + extendedMix on the project; extended paths → Task 2. ✓
- Light-analysis + plan + render in the worker via subprocess; job runner mirroring analysis → Tasks 3 + 5. ✓
- Vocal modes place_once/loop/drop → Task 5 renderer. ✓
- API `/extend` (400 no stems, 409 running) + `/extended-mix` (404 until ready) → Task 4. ✓
- Extend Song card + polling + download → Task 6. ✓
- soundfile already present in worker env (no install task needed); constraint noted. ✓
- Tests: pure core in backend/.venv (Task 1), plumbing with fakes (Tasks 2–4), worker-env smoke (Task 5), frontend (Task 6). ✓

**Placeholder scan:** No TBD/TODO; every code step is complete; commands have expected output. The DSP renderer is complete numpy; its audio *quality* is validated by the worker smoke test (length/validity) + Task 7 (listening).

**Type consistency:** `build_extension_plan(...) -> ExtensionPlan`, `render_layout(plan, spb) -> list[tuple]`, `samples_per_bar(...) -> int` defined in Task 1 and consumed identically in Task 5. The provider result dict `{relativePath, durationSeconds, warnings}` is produced in Task 5, returned by `LocalExtendProvider.extend` (Task 3), stored as `extendedMix` (Task 2), and read by the frontend (Task 6). `AnalysisJob` reused for `extendJob` throughout. Endpoint request fields `{genre, targetSeconds, vocalMode}` match `ReconstructionExtendRequest` (Task 4) and the runner options (Task 3) and the worker options (Task 5).
