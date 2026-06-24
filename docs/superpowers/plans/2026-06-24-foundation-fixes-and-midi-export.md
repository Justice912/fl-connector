# Foundation Fixes + One-Drag MIDI Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the six confirmed correctness bugs in the FL Connector and add a dependency-free, one-drag multi-track MIDI export so a whole generated song lands in FL Studio in a single action.

**Architecture:** Backend is FastAPI (`backend/app`), frontend is React/Vite (`frontend/src`). Phase 0 fixes the generator dispatch, the analysis-job concurrency/recovery, store resilience/atomicity, and migrates startup to a lifespan handler. Phase 1 adds a self-contained Standard MIDI File writer (`backend/app/midi_export.py`), two download endpoints, and frontend export buttons.

**Tech Stack:** Python 3.11, FastAPI, pytest (backend venv at `backend/.venv`); React 18, Vite, Vitest, @testing-library/react (frontend).

**Working directory for all paths:** `C:\Users\HP\Vocals APP\fl-connector`
**Backend test command:** `cd backend && ./.venv/Scripts/python -m pytest -q`
**Branch:** `phase-0-1-foundation-midi` (already created; the design spec is committed here).

**Spec:** `docs/superpowers/specs/2026-06-24-foundation-fixes-and-midi-export-design.md`

---

## Task 1: Genre-correct song generation (Phase 0.1)

Currently `generate_song_draft` routes afro/hip/trap genres to a single melody part while the arrangement references parts that do not exist, and "trap" dispatches inconsistently. Make every genre produce a coherent multi-part draft whose arrangement only references present roles.

**Files:**
- Modify: `backend/app/generator.py`
- Test: `backend/tests/test_generator.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_generator.py`:

```python
import pytest

from app.generator import generate_payload, generate_song_draft, genre_family


@pytest.mark.parametrize("genre", ["Amapiano", "Afrobeats", "Afrohouse", "Hip Hop", "Trap"])
def test_song_draft_parts_and_arrangement_are_coherent(genre):
    draft = generate_song_draft(prompt=f"Create a {genre} song", genre=genre, bars=8)
    roles = {part.role for part in draft.parts}
    assert len(draft.parts) >= 4
    assert len(draft.arrangement) == 4
    for section in draft.arrangement:
        assert section.activeParts, "arrangement section must list active parts"
        assert set(section.activeParts) <= roles


def test_trap_uses_same_family_for_single_and_song():
    assert genre_family("Trap") == genre_family("Hip Hop") == "hiphop"
    draft = generate_song_draft(prompt="dark trap song", genre="Trap")
    assert {part.role for part in draft.parts} == {"drums", "bass", "chords", "melody"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_generator.py -q`
Expected: FAIL — `ImportError: cannot import name 'genre_family'`.

- [ ] **Step 3: Add the genre dispatch helper and route both generators through it**

In `backend/app/generator.py`, add after `infer_title` (before `generate_payload`):

```python
def genre_family(genre: str) -> str:
    lowered = genre.strip().lower()
    if "amapiano" in lowered:
        return "amapiano"
    if "afro" in lowered:
        return "afro"
    if "hip" in lowered or "trap" in lowered:
        return "hiphop"
    return "amapiano"
```

Replace the body of `generate_payload` dispatch (the `if "afro"...` block) with:

```python
    key = normalize_key(key)
    scale = infer_scale(prompt, scale)
    family = genre_family(genre)
    if family == "afro":
        return _generate_afro_payload(prompt, genre, bpm, key, scale, bars)
    if family == "hiphop":
        return _generate_hiphop_payload(prompt, genre, bpm, key, scale, bars)
    return _generate_amapiano_payload(prompt, genre, bpm, key, scale, bars)
```

Replace the whole body of `generate_song_draft` with:

```python
    key = normalize_key(key)
    scale = infer_scale(prompt, scale)
    family = genre_family(genre)
    if family == "amapiano":
        return _generate_amapiano_song(prompt, genre, bpm, key, scale, bars)
    return _generate_generic_song(family, prompt, genre, bpm, key, scale, bars)
```

- [ ] **Step 4: Add the shared melody builders, generic part builders, and generic song**

In `backend/app/generator.py`, replace `_generate_afro_payload` and `_generate_hiphop_payload` with shared note builders plus thin payload wrappers, and add the generic song builder. Add this block (replacing the two old afro/hiphop payload functions):

```python
def _afro_melody(key: str, scale: str, bars: int) -> list[Note]:
    pool = _scale_notes(key, "major" if scale == "major" else scale)
    root = pool[0]
    motif = [(0.0, 7), (0.5, 9), (1.25, 4), (1.75, 7), (2.5, 2), (3.25, 4)]
    return [
        Note(root + degree + 12, bar * 4 + offset, 0.42, 0.74, 3)
        for bar in range(bars)
        for offset, degree in motif
    ]


def _hiphop_melody(key: str, scale: str, bars: int) -> list[Note]:
    pool = _scale_notes(key, scale)
    root = pool[0]
    motif = [(0.0, 0), (0.75, 3), (1.5, 7), (2.5, 10), (3.0, 7)]
    return [
        Note(root + interval + 12, bar * 4 + offset, 0.5, 0.72, 4)
        for bar in range(bars)
        for offset, interval in motif
    ]


def _generic_drums(bars: int) -> list[Note]:
    notes: list[Note] = []
    for bar in range(bars):
        base = bar * 4
        for beat in range(4):
            notes.append(Note(36, base + beat, 0.2, 0.9, 5))
        for beat in (1, 3):
            notes.append(Note(39, base + beat, 0.16, 0.7, 3))
        for step in range(8):
            notes.append(Note(42, base + step * 0.5, 0.1, 0.5 if step % 2 else 0.6, 2))
    return notes


def _generic_bass(key: str, scale: str, bars: int) -> list[Note]:
    pool = _scale_notes(key, scale)
    root = pool[0] - 12
    fifth = pool[4] - 12
    notes: list[Note] = []
    for bar in range(bars):
        base = bar * 4
        notes.append(Note(root, base, 0.9, 0.74, 5))
        notes.append(Note(root, base + 1.5, 0.5, 0.6, 5))
        notes.append(Note(fifth, base + 2.5, 0.5, 0.64, 5))
        notes.append(Note(root, base + 3.5, 0.4, 0.56, 5))
    return notes


_FAMILY_MELODY = {"afro": _afro_melody, "hiphop": _hiphop_melody}
_FAMILY_PATTERN_NAMES = {
    "afro": {
        "drums": "Afrobeats kit groove",
        "bass": "Rolling afro bass",
        "chords": "Bright afro chords",
        "melody": "Afro lead motif",
    },
    "hiphop": {
        "drums": "Boom-bap kit",
        "bass": "808 sub bass",
        "chords": "Sampled chord stab",
        "melody": "Hip-hop lead hook",
    },
}
_FAMILY_PLUGIN_HINTS = {
    "afro": {
        "drums": "FPC - afro kit",
        "bass": "3xOsc or FLEX bass, keep centered",
        "chords": "FLEX keys or pad",
        "melody": "FLEX pluck or marimba preset",
    },
    "hiphop": {
        "drums": "FPC - boom-bap kit",
        "bass": "3xOsc 808 sub",
        "chords": "FLEX keys or sampler stab",
        "melody": "FLEX lead preset",
    },
}


def _generate_afro_payload(
    prompt: str, genre: str, bpm: int, key: str, scale: str, bars: int
) -> NotePayload:
    return _payload(
        title=infer_title(prompt, genre),
        prompt=prompt,
        genre=genre,
        bpm=bpm,
        key=key,
        scale=scale,
        bars=bars,
        notes=_afro_melody(key, scale, bars),
    )


def _generate_hiphop_payload(
    prompt: str, genre: str, bpm: int, key: str, scale: str, bars: int
) -> NotePayload:
    return _payload(
        title=infer_title(prompt, genre),
        prompt=prompt,
        genre=genre,
        bpm=bpm,
        key=key,
        scale=scale,
        bars=bars,
        notes=_hiphop_melody(key, scale, bars),
    )


def _generate_generic_song(
    family: str, prompt: str, genre: str, bpm: int, key: str, scale: str, bars: int
) -> SongDraft:
    names = _FAMILY_PATTERN_NAMES[family]
    hints = _FAMILY_PLUGIN_HINTS[family]
    melody_builder = _FAMILY_MELODY[family]
    role_notes = {
        "drums": _generic_drums(bars),
        "bass": _generic_bass(key, scale, bars),
        "chords": _amapiano_chords(key, scale, bars),
        "melody": melody_builder(key, scale, bars),
    }
    roles = ["drums", "bass", "chords", "melody"]
    parts = [
        SongPart.create(
            role=role,
            patternName=names[role],
            pluginHint=hints[role],
            applyOrder=index + 1,
            payload=_payload(
                title=names[role],
                prompt=f"{prompt} | {role}",
                genre=genre,
                bpm=bpm,
                key=key,
                scale=scale,
                bars=bars,
                notes=role_notes[role],
            ),
        )
        for index, role in enumerate(roles)
    ]
    return SongDraft.create(
        title=f"{genre} full draft",
        sourcePrompt=prompt,
        genre=genre,
        bpm=bpm,
        key=key,
        scale=scale,
        bars=bars,
        parts=parts,
        arrangement=_arrangement(bars, roles),
    )
```

- [ ] **Step 5: Make `_arrangement` filter active parts by available roles**

In `backend/app/generator.py`, replace the entire `_arrangement` function with:

```python
def _arrangement(
    bars: int,
    roles: tuple[str, ...] | list[str] = ("drums", "bass", "chords", "log_drum", "melody"),
) -> list[ArrangementSection]:
    available = set(roles)
    if bars >= 16:
        lengths = [4, 4, 4, bars - 12]
    elif bars >= 8:
        lengths = [2, 2, 2, bars - 6]
    else:
        lengths = [1, 1, 1, max(1, bars - 3)]
    starts = [1]
    for length in lengths[:-1]:
        starts.append(starts[-1] + length)
    plan = [
        ("Intro", ["chords", "drums"]),
        ("Groove", ["drums", "bass", "chords"]),
        ("Drop", ["drums", "bass", "chords", "log_drum"]),
        ("Hook", ["drums", "bass", "chords", "log_drum", "melody"]),
    ]
    sections: list[ArrangementSection] = []
    for index, (name, parts) in enumerate(plan):
        active = [part for part in parts if part in available] or sorted(available)
        sections.append(ArrangementSection(name, starts[index], lengths[index], active))
    return sections
```

Note: `_generate_amapiano_song` already calls `_arrangement(bars)`; the default roles keep its output identical, so the existing amapiano test still passes.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_generator.py -q`
Expected: PASS (4 tests: the 2 original + 2 new).

- [ ] **Step 7: Run the full backend suite**

Run: `cd backend && ./.venv/Scripts/python -m pytest -q`
Expected: PASS (70 passed — the prior 68 plus 2 new).

- [ ] **Step 8: Commit**

```bash
git add backend/app/generator.py backend/tests/test_generator.py
git commit -m "fix: generate coherent multi-part songs for every genre

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Resilient events + atomic FL-file writes (Phase 0.4 + 0.5)

Make `events()` tolerate malformed log lines (so `/api/health` and `/api/events` cannot 500), and write all FL-facing JSON atomically so FL never reads a half-written file.

**Files:**
- Modify: `backend/app/store.py`
- Test: `backend/tests/test_store.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_store.py`:

```python
from app.store import PayloadStore, _atomic_write_text


def test_atomic_write_replaces_content_without_residue(tmp_path):
    target = tmp_path / "x.json"
    _atomic_write_text(target, "one")
    _atomic_write_text(target, "two")
    assert target.read_text(encoding="utf-8") == "two"
    assert list(tmp_path.glob("*.tmp")) == []


def test_events_skip_malformed_lines(tmp_path):
    store = PayloadStore(tmp_path)
    store.ensure()
    store.event("a", "first")
    with store.events_path.open("a", encoding="utf-8") as handle:
        handle.write("{ broken json line\n")
        handle.write("\n")
    store.event("b", "second")
    messages = [row["message"] for row in store.events()]
    assert messages == ["first", "second"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_store.py -q`
Expected: FAIL — `ImportError: cannot import name '_atomic_write_text'`.

- [ ] **Step 3: Add the atomic-write helper**

In `backend/app/store.py`, change the imports at the top from:

```python
from __future__ import annotations

import json
from pathlib import Path
```

to:

```python
from __future__ import annotations

import json
import os
from pathlib import Path
```

Then add this module-level function immediately after the imports (before `class PayloadStore`):

```python
def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
```

- [ ] **Step 4: Use atomic writes for every JSON write and harden `events()`**

In `backend/app/store.py`, replace each `<path>.write_text(<json>, encoding="utf-8")` call in these methods with `_atomic_write_text(<path>, <json>)`. Concretely:

`save_draft`:
```python
        path = self.drafts_dir / f"{payload.id}.json"
        _atomic_write_text(path, json.dumps(payload.to_dict(), indent=2))
```

`approve`:
```python
        fl_payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_json = json.dumps(payload.to_dict(), indent=2)
        _atomic_write_text(fl_payload_path, payload_json)
        _atomic_write_text(self.drafts_dir / f"{payload.id}.json", payload_json)
        _atomic_write_text(self.current_path, payload_json)
```

`save_song_draft`:
```python
        draft_json = json.dumps(draft.to_dict(), indent=2)
        _atomic_write_text(self.songs_dir / f"{draft.id}.json", draft_json)
        _atomic_write_text(self.current_song_path, draft_json)
```

`save_mastering_plan`:
```python
        plan_json = json.dumps(plan.to_dict(), indent=2)
        _atomic_write_text(self.mastering_dir / f"{plan.id}.json", plan_json)
        _atomic_write_text(self.current_mastering_path, plan_json)
```

`approve_mastering_plan`:
```python
        fl_plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_json = json.dumps(plan.to_dict(), indent=2)
        _atomic_write_text(fl_plan_path, plan_json)
        _atomic_write_text(self.mastering_dir / f"{plan.id}.json", plan_json)
        _atomic_write_text(self.current_mastering_path, plan_json)
```

Replace the `events()` method body with a malformed-line-tolerant version:

```python
    def events(self, limit: int = 50) -> list[dict[str, object]]:
        if not self.events_path.exists():
            return []
        rows: list[dict[str, object]] = []
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
        return rows[-limit:]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_store.py -q`
Expected: PASS (2 tests).

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && ./.venv/Scripts/python -m pytest -q`
Expected: PASS (72 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/app/store.py backend/tests/test_store.py
git commit -m "fix: atomic FL-file writes and malformed-event resilience

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Analysis concurrency, interrupted-job recovery, lifespan migration (Phase 0.2 + 0.3 + 0.6)

Make the analysis runner a shared singleton (so its lock actually serializes jobs), recover interrupted jobs on startup, and migrate the deprecated `on_event` startup to a FastAPI lifespan handler.

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_analysis_jobs.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_analysis_jobs.py` (top-level imports first):

```python
import threading

import pytest

from app.reconstruction_contracts import AnalysisJob, ReconstructionError
```

Then add these tests:

```python
def test_runner_rejects_second_concurrent_job(tmp_path: Path):
    store = ReconstructionStore(tmp_path)
    project = project_with_stem(store)
    started = threading.Event()
    release = threading.Event()

    class BlockingProvider:
        def analyze(self, project_path, progress):
            started.set()
            release.wait(2)
            return SuccessfulProvider().analyze(project_path, progress)

    runner = AnalysisJobRunner(
        store,
        BlockingProvider(),
        ReconstructionCompiler(),
        inventory_provider=lambda: InventorySnapshot.empty(),
    )

    runner.start(project.id)
    assert started.wait(2), "background analysis did not start"
    try:
        with pytest.raises(ReconstructionError):
            runner.run(project.id)
    finally:
        release.set()


def test_mark_interrupted_jobs_resets_running_projects(tmp_path: Path):
    store = ReconstructionStore(tmp_path)
    project = project_with_stem(store)
    running = AnalysisJob.create().with_progress(
        status="running", progress=25, stage="analyzing", message="Working"
    )
    store.save(project.with_changes(status="analyzing", analysisJob=running))
    runner = AnalysisJobRunner(
        store,
        SuccessfulProvider(),
        ReconstructionCompiler(),
        inventory_provider=lambda: InventorySnapshot.empty(),
    )

    changed = runner.mark_interrupted_jobs()

    assert project.id in changed
    reread = store.get(project.id)
    assert reread.status == "error"
    assert reread.analysisJob.status == "interrupted"
```

- [ ] **Step 2: Run tests to verify they pass or fail appropriately**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_analysis_jobs.py -q`
Expected: PASS — these exercise existing `AnalysisJobRunner` behavior (the singleton/lifespan wiring in main.py is what changes; these tests lock in the runner contract the wiring relies on). If either fails, fix the runner before proceeding.

- [ ] **Step 3: Make `_analysis_runner` a singleton in main.py**

In `backend/app/main.py`, add a module global next to the other module-level constants (after `DEFAULT_CORS_ORIGINS = (...)` near line 41):

```python
_ANALYSIS_RUNNER: AnalysisJobRunner | None = None
```

Replace the existing `_analysis_runner` function near the bottom of the file with:

```python
def _analysis_runner() -> AnalysisJobRunner:
    global _ANALYSIS_RUNNER
    if _ANALYSIS_RUNNER is None:
        catalog = InventoryScanner.load_catalog(CATALOG_PATH)
        _ANALYSIS_RUNNER = AnalysisJobRunner(
            RECONSTRUCTION_STORE,
            LocalAnalysisProvider(worker_python(APP_ROOT), APP_ROOT / "backend"),
            ReconstructionCompiler(catalog),
            inventory_provider=_scan_inventory,
        )
    return _ANALYSIS_RUNNER
```

- [ ] **Step 4: Migrate startup to a lifespan handler**

In `backend/app/main.py`, change the standard-library import line:

```python
import json
import os
```

to:

```python
import json
import os
from contextlib import asynccontextmanager
```

Add the lifespan function immediately before `app = FastAPI(...)` (after `_parse_cors_origins`):

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    STORE.ensure()
    RECONSTRUCTION_STORE.ensure()
    STORE.event("server", "Connector backend started")
    try:
        recovered = _analysis_runner().mark_interrupted_jobs()
        if recovered:
            STORE.event("server", f"Reset {len(recovered)} interrupted analysis job(s)")
    except Exception as exc:  # startup must never crash the server
        STORE.event("error", f"Startup interrupted-job sweep failed: {exc}")
    yield
```

Change the app constructor to register it:

```python
app = FastAPI(title="FL Connector", version="0.1.0", lifespan=lifespan)
```

Delete the now-obsolete startup hook (the whole block):

```python
@app.on_event("startup")
def startup() -> None:
    STORE.ensure()
    RECONSTRUCTION_STORE.ensure()
    STORE.event("server", "Connector backend started")
```

- [ ] **Step 5: Verify the app imports and startup runs under lifespan**

Run: `cd backend && ./.venv/Scripts/python -c "from fastapi.testclient import TestClient; from app.main import app;\nwith TestClient(app) as c:\n    print(c.get('/api/health').status_code)"`
Expected: prints `200` with no `on_event` deprecation warning from app code.

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && ./.venv/Scripts/python -m pytest -q`
Expected: PASS (74 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/app/main.py backend/tests/test_analysis_jobs.py
git commit -m "fix: shared analysis runner, interrupted-job recovery, lifespan startup

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Accurate connector architecture doc (Phase 0.6)

The outer `Vocals APP/docs/ARCHITECTURE.md` describes an unrelated project. Add an accurate architecture doc inside the connector repo. (Do not modify the outer file.)

**Files:**
- Create: `docs/ARCHITECTURE.md` (inside `fl-connector`)

- [ ] **Step 1: Write the doc**

Create `docs/ARCHITECTURE.md`:

```markdown
# FL Connector Architecture

Local-first Windows tool for FL Studio 2025. Backend: FastAPI (`backend/app`,
port 8765). Frontend: React/Vite (`frontend/src`, port 5173). All data stays
local under `.data/`.

## Backend modules (`backend/app`)

- `main.py` — FastAPI app, routes, lifespan startup. Holds the singleton
  `PayloadStore`, `ReconstructionStore`, and analysis runner.
- `contracts.py` — frozen dataclasses + validation for notes, payloads, song
  drafts, mastering plans, and bridge snapshots.
- `generator.py` — deterministic prompt-to-notes and prompt-to-song generation,
  dispatched by genre family (amapiano / afro / hiphop).
- `mastering.py` — built-in-FX mixer/master chain plan generation.
- `midi_export.py` — dependency-free Standard MIDI File (type 1) writer for
  one-drag export of songs and single payloads.
- `store.py` — JSON persistence with atomic writes and an append-only event log.
- `paths.py` / `fl_scripts.py` — FL Studio user-data path detection and Piano
  Roll script installation.
- `bridge.py` / `bridge_setup.py` — Flapi live bridge: read-only snapshot,
  transport play/stop, and setup checks.
- `analysis*.py`, `inventory.py`, `reconstruction_*.py` — the Audio-to-FL
  Rebuild pipeline (stem upload, local analysis worker, compilation, export).

## FL Studio integration surfaces

1. **Piano Roll script** — `approve` writes `pending_payload.json`; the installed
   `.pyscript` reads it and calls `flp.score.addNote(...)`. One part at a time.
2. **One-drag MIDI** — `/api/songs/{id}/export-midi` produces a multi-track `.mid`
   the user drags into FL once; each part becomes its own channel/pattern.
3. **Mastering plan** — `approved_mastering_plan.json` plus exact mixer click-paths.
4. **Live bridge (Flapi)** — read-only mixer/transport snapshot + play/stop over
   loopMIDI. Deeper live writes are a later phase.

## Data flow (generate path)

prompt -> `generate_song_draft` -> `PayloadStore.save_song_draft` ->
(approve part -> `pending_payload.json` + Piano Roll script) and/or
(export -> multi-track `.mid` dragged into FL).
```

- [ ] **Step 2: Commit**

```bash
git add docs/ARCHITECTURE.md
git commit -m "docs: add accurate FL Connector architecture overview

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Standard MIDI File writer (Phase 1.1)

A self-contained, dependency-free SMF type-1 writer. No `mido`.

**Files:**
- Create: `backend/app/midi_export.py`
- Test: `backend/tests/test_midi_export.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_midi_export.py`:

```python
from app.generator import generate_payload, generate_song_draft
from app.midi_export import payload_to_midi, song_to_midi


def _read_vlq(data: bytes, index: int) -> tuple[int, int]:
    value = 0
    while True:
        byte = data[index]
        index += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, index


def _parse_track(body: bytes) -> dict:
    index = 0
    abs_tick = 0
    name = None
    tempo = None
    notes: list[tuple[int, int, int, int]] = []
    while index < len(body):
        delta, index = _read_vlq(body, index)
        abs_tick += delta
        status = body[index]
        index += 1
        if status == 0xFF:
            meta = body[index]
            index += 1
            length, index = _read_vlq(body, index)
            chunk = body[index : index + length]
            index += length
            if meta == 0x03:
                name = chunk.decode("utf-8")
            elif meta == 0x51:
                tempo = int.from_bytes(chunk, "big")
            elif meta == 0x2F:
                break
        elif status & 0xF0 in (0x80, 0x90):
            pitch = body[index]
            velocity = body[index + 1]
            index += 2
            if status & 0xF0 == 0x90 and velocity > 0:
                notes.append((abs_tick, pitch, velocity, status & 0x0F))
        else:  # pragma: no cover - writer never emits other channel events
            index += 2
    return {"name": name, "tempo": tempo, "notes": notes}


def parse_midi(data: bytes) -> dict:
    assert data[:4] == b"MThd"
    fmt = int.from_bytes(data[8:10], "big")
    ntrks = int.from_bytes(data[10:12], "big")
    division = int.from_bytes(data[12:14], "big")
    tracks = []
    index = 14
    for _ in range(ntrks):
        assert data[index : index + 4] == b"MTrk"
        length = int.from_bytes(data[index + 4 : index + 8], "big")
        body = data[index + 8 : index + 8 + length]
        index += 8 + length
        tracks.append(_parse_track(body))
    return {"format": fmt, "ntrks": ntrks, "division": division, "tracks": tracks}


def test_song_to_midi_has_track_per_part_tempo_and_notes():
    draft = generate_song_draft(
        prompt="deep amapiano song", genre="Amapiano", bpm=120, key="A", scale="minor", bars=4
    )
    parsed = parse_midi(song_to_midi(draft))

    assert parsed["format"] == 1
    assert parsed["division"] == 96
    assert parsed["ntrks"] == len(draft.parts) + 1
    assert parsed["tracks"][0]["tempo"] == round(60_000_000 / 120)

    ordered = sorted(draft.parts, key=lambda part: part.applyOrder)
    assert [track["name"] for track in parsed["tracks"][1:]] == [part.patternName for part in ordered]

    total_src = sum(len(part.payload.notes) for part in draft.parts)
    total_mid = sum(len(track["notes"]) for track in parsed["tracks"][1:])
    assert total_mid == total_src


def test_payload_to_midi_round_trips_notes_and_ticks():
    payload = generate_payload(prompt="amapiano log drum", genre="Amapiano", key="C", bpm=110, bars=2)
    parsed = parse_midi(payload_to_midi(payload))

    assert parsed["ntrks"] == 2
    assert len(parsed["tracks"][1]["notes"]) == len(payload.notes)

    lowest_start = min(note.startBeats for note in payload.notes)
    ticks = sorted(note[0] for note in parsed["tracks"][1]["notes"])
    assert ticks[0] == round(lowest_start * 96)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_midi_export.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.midi_export'`.

- [ ] **Step 3: Implement the writer**

Create `backend/app/midi_export.py`:

```python
from __future__ import annotations

from .contracts import Note, NotePayload, SongDraft

PPQ = 96


def _vlq(value: int) -> bytes:
    if value < 0:
        raise ValueError("variable-length quantity must be non-negative")
    chunks = [value & 0x7F]
    value >>= 7
    while value:
        chunks.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(chunks))


def _note_events(notes: list[Note], channel: int) -> list[tuple[int, int, int, int, int]]:
    events: list[tuple[int, int, int, int, int]] = []
    for note in notes:
        start = max(0, round(note.startBeats * PPQ))
        duration = max(1, round(note.durationBeats * PPQ))
        pitch = max(0, min(127, int(note.pitch)))
        velocity = max(1, min(127, round(note.velocity * 127)))
        # order 1 = note-on, 0 = note-off, so note-off sorts first at equal ticks
        events.append((start, 1, 0x90 | channel, pitch, velocity))
        events.append((start + duration, 0, 0x80 | channel, pitch, 0))
    events.sort(key=lambda event: (event[0], event[1]))
    return events


def _meta(meta_type: int, payload: bytes) -> bytes:
    return b"\xff" + bytes([meta_type]) + _vlq(len(payload)) + payload


def _track_chunk(body: bytes) -> bytes:
    return b"MTrk" + len(body).to_bytes(4, "big") + body


def _encode_track(events: list[tuple[int, int, int, int, int]], name: str) -> bytes:
    name_bytes = name.encode("utf-8", "replace")[:127]
    body = bytearray()
    body += _vlq(0) + _meta(0x03, name_bytes)
    previous_tick = 0
    for tick, _order, status, data1, data2 in events:
        body += _vlq(tick - previous_tick) + bytes([status, data1, data2])
        previous_tick = tick
    body += _vlq(0) + _meta(0x2F, b"")
    return _track_chunk(bytes(body))


def _conductor_track(title: str, bpm: int) -> bytes:
    title_bytes = title.encode("utf-8", "replace")[:127]
    tempo = round(60_000_000 / bpm)
    body = bytearray()
    body += _vlq(0) + _meta(0x03, title_bytes)
    body += _vlq(0) + _meta(0x51, tempo.to_bytes(3, "big"))
    body += _vlq(0) + _meta(0x58, bytes([4, 2, 24, 8]))  # 4/4
    body += _vlq(0) + _meta(0x2F, b"")
    return _track_chunk(bytes(body))


def _header(track_count: int) -> bytes:
    return (
        b"MThd"
        + (6).to_bytes(4, "big")
        + (1).to_bytes(2, "big")
        + track_count.to_bytes(2, "big")
        + PPQ.to_bytes(2, "big")
    )


def song_to_midi(draft: SongDraft) -> bytes:
    tracks = [_conductor_track(draft.title, draft.bpm)]
    ordered = sorted(draft.parts, key=lambda part: part.applyOrder)
    for index, part in enumerate(ordered):
        events = _note_events(part.payload.notes, index % 16)
        tracks.append(_encode_track(events, part.patternName))
    return _header(len(tracks)) + b"".join(tracks)


def payload_to_midi(payload: NotePayload) -> bytes:
    tracks = [
        _conductor_track(payload.title, payload.bpm),
        _encode_track(_note_events(payload.notes, 0), payload.title),
    ]
    return _header(len(tracks)) + b"".join(tracks)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_midi_export.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && ./.venv/Scripts/python -m pytest -q`
Expected: PASS (76 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/midi_export.py backend/tests/test_midi_export.py
git commit -m "feat: add dependency-free multi-track MIDI writer

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: MIDI export endpoints (Phase 1.2)

Expose downloadable `.mid` for a song draft and for a single payload.

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_midi_export_api.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_midi_export_api.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app.paths import detect_paths
from app.store import PayloadStore


def isolated_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr(main, "STORE", PayloadStore(tmp_path / "payloads"))
    monkeypatch.setattr(main, "detect_paths", lambda: detect_paths(tmp_path))
    return TestClient(main.app)


def test_export_song_midi_returns_midi_file(tmp_path: Path, monkeypatch):
    client = isolated_client(tmp_path, monkeypatch)
    draft = client.post(
        "/api/songs/generate",
        json={"prompt": "deep amapiano song draft", "bars": 8},
    ).json()

    response = client.get(f"/api/songs/{draft['id']}/export-midi")

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/midi"
    assert ".mid" in response.headers["content-disposition"]
    assert response.content[:4] == b"MThd"


def test_export_payload_midi_returns_midi_file(tmp_path: Path, monkeypatch):
    client = isolated_client(tmp_path, monkeypatch)
    payload = client.post(
        "/api/generate",
        json={"prompt": "amapiano log drum riff"},
    ).json()

    response = client.get(f"/api/payloads/{payload['id']}/export-midi")

    assert response.status_code == 200
    assert response.content[:4] == b"MThd"


def test_export_song_midi_unknown_id_returns_404(tmp_path: Path, monkeypatch):
    client = isolated_client(tmp_path, monkeypatch)
    response = client.get("/api/songs/does-not-exist/export-midi")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_midi_export_api.py -q`
Expected: FAIL — 404s become "Not Found" route-missing for `/export-midi`, so `test_export_song_midi_returns_midi_file` fails on status 200.

- [ ] **Step 3: Add the import and endpoints**

In `backend/app/main.py`, add to the app-module imports (next to `from .generator import ...`):

```python
from .midi_export import payload_to_midi, song_to_midi
```

Add a filename helper and the two endpoints (place them after the `current_song` endpoint, before the mastering endpoints):

```python
def _safe_filename(title: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "_" for char in title)
    return cleaned.strip("_")


@app.get("/api/songs/{song_id}/export-midi")
def export_song_midi(song_id: str) -> Response:
    try:
        draft = STORE.get_song(song_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="song draft not found") from exc
    data = song_to_midi(draft)
    filename = _safe_filename(draft.title) or "song"
    return Response(
        content=data,
        media_type="audio/midi",
        headers={"Content-Disposition": f'attachment; filename="{filename}.mid"'},
    )


@app.get("/api/payloads/{payload_id}/export-midi")
def export_payload_midi(payload_id: str) -> Response:
    try:
        payload = STORE.get(payload_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="payload not found") from exc
    data = payload_to_midi(payload)
    filename = _safe_filename(payload.title) or "payload"
    return Response(
        content=data,
        media_type="audio/midi",
        headers={"Content-Disposition": f'attachment; filename="{filename}.mid"'},
    )
```

(`Response` is already imported from `fastapi` in main.py.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_midi_export_api.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && ./.venv/Scripts/python -m pytest -q`
Expected: PASS (79 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/tests/test_midi_export_api.py
git commit -m "feat: add MIDI export endpoints for songs and payloads

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Frontend MIDI export buttons (Phase 1.3)

Add API helpers and "Download Song MIDI (all parts)" + per-part download buttons, with a drag-into-FL hint.

**Files:**
- Modify: `frontend/src/api.js`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/App.test.jsx` (create)

- [ ] **Step 1: Add the API helpers**

In `frontend/src/api.js`, add these two entries to the `api` object (after the `events` line):

```javascript
  exportSongMidi: (id) => download(`/api/songs/${id}/export-midi`, `song-${id}.mid`),
  exportPayloadMidi: (id) => download(`/api/payloads/${id}/export-midi`, `part-${id}.mid`),
```

- [ ] **Step 2: Write the failing component test**

Create `frontend/src/App.test.jsx`:

```jsx
import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import { SongDraftPanel } from './App';

function sampleSong() {
  return {
    id: 'song-1',
    title: 'Amapiano full draft',
    parts: [
      {
        id: 'p1',
        applyOrder: 1,
        patternName: 'FPC bounce drums',
        pluginHint: 'FPC',
        payload: { id: 'pay1', notes: [] },
      },
    ],
    arrangement: [{ name: 'Intro', startBar: 1, bars: 2, activeParts: ['drums'] }],
  };
}

test('song panel triggers a full-song MIDI export', () => {
  const onExportSong = vi.fn();
  render(
    <SongDraftPanel
      song={sampleSong()}
      selectedPartId=""
      onSelectPart={() => {}}
      onExportSong={onExportSong}
      onExportPart={() => {}}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /download song midi/i }));
  expect(onExportSong).toHaveBeenCalledTimes(1);
});

test('song panel triggers a per-part MIDI export', () => {
  const onExportPart = vi.fn();
  render(
    <SongDraftPanel
      song={sampleSong()}
      selectedPartId=""
      onSelectPart={() => {}}
      onExportSong={() => {}}
      onExportPart={onExportPart}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /download fpc bounce drums midi/i }));
  expect(onExportPart).toHaveBeenCalledTimes(1);
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && npm test -- App.test.jsx`
Expected: FAIL — `SongDraftPanel` is not exported / buttons not found.

- [ ] **Step 4: Export `SongDraftPanel` and add the buttons**

In `frontend/src/App.jsx`, change the declaration:

```jsx
function SongDraftPanel({ song, selectedPartId, onSelectPart }) {
```

to:

```jsx
export function SongDraftPanel({ song, selectedPartId, onSelectPart, onExportSong, onExportPart }) {
```

Replace the `part-list` block and add a song-actions row. Replace this existing markup:

```jsx
      <div className="part-list">
        {song.parts.map((part) => (
          <button
            type="button"
            className={`part-row ${part.id === selectedPartId ? 'active' : ''}`}
            key={part.id}
            onClick={() => onSelectPart(part)}
          >
            <span>{part.applyOrder}</span>
            <strong>{part.patternName}</strong>
            <em>{part.pluginHint}</em>
            <small>{part.payload.notes.length} notes</small>
          </button>
        ))}
      </div>
```

with:

```jsx
      <div className="song-actions">
        <button type="button" className="secondary-button" onClick={onExportSong}>
          <Download size={18} />
          Download Song MIDI (all parts)
        </button>
        <span className="song-hint">
          Drag the .mid into the FL Studio Playlist or onto a Channel Rack slot — each track
          becomes its own channel/pattern.
        </span>
      </div>
      <div className="part-list">
        {song.parts.map((part) => (
          <div className="part-row-wrap" key={part.id}>
            <button
              type="button"
              className={`part-row ${part.id === selectedPartId ? 'active' : ''}`}
              onClick={() => onSelectPart(part)}
            >
              <span>{part.applyOrder}</span>
              <strong>{part.patternName}</strong>
              <em>{part.pluginHint}</em>
              <small>{part.payload.notes.length} notes</small>
            </button>
            <button
              type="button"
              className="icon-button"
              aria-label={`Download ${part.patternName} MIDI`}
              onClick={() => onExportPart(part)}
            >
              <Download size={16} />
            </button>
          </div>
        ))}
      </div>
```

- [ ] **Step 5: Wire the handlers in the `App` component**

In `frontend/src/App.jsx`, replace the existing `<SongDraftPanel ... />` usage with:

```jsx
        <SongDraftPanel
          song={song}
          selectedPartId={selectedPartId}
          onSelectPart={(part) => {
            setSelectedPartId(part.id);
            setPayload(part.payload);
            setMessage(`Selected ${part.patternName}.`);
          }}
          onExportSong={() => runTask(async () => {
            await api.exportSongMidi(song.id);
            setMessage('Song MIDI exported. Drag the .mid into FL Studio.');
          }, { adoptCurrent: false })}
          onExportPart={(part) => runTask(async () => {
            await api.exportPayloadMidi(part.payload.id);
            setMessage(`Exported ${part.patternName} MIDI.`);
          }, { adoptCurrent: false })}
        />
```

- [ ] **Step 6: Add minimal styling**

In `frontend/src/styles.css`, append:

```css
.song-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}

.song-hint {
  font-size: 12px;
  opacity: 0.75;
}

.part-row-wrap {
  display: flex;
  align-items: stretch;
  gap: 6px;
}

.part-row-wrap .part-row {
  flex: 1;
}
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `cd frontend && npm test -- App.test.jsx`
Expected: PASS (2 tests).

- [ ] **Step 8: Run the full frontend suite and build**

Run: `cd frontend && npm test`
Expected: PASS (all existing + 2 new).

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/api.js frontend/src/App.jsx frontend/src/styles.css frontend/src/App.test.jsx
git commit -m "feat: add one-drag MIDI export buttons to the song draft panel

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Live FL Studio acceptance (Phase 1.4)

Manual verification with FL Studio 2025 (the user has Flapi + loopMIDI set up). Not a code task.

- [ ] **Step 1: Start backend and frontend**

```powershell
cd 'C:\Users\HP\Vocals APP\fl-connector\backend'
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```
```powershell
cd 'C:\Users\HP\Vocals APP\fl-connector\frontend'
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

- [ ] **Step 2: Generate and export**

Open `http://127.0.0.1:5173`, click **Generate Song Draft**, then **Download Song MIDI (all parts)**.

- [ ] **Step 3: Drag into FL Studio 2025**

Drag the `.mid` into the FL Studio Playlist. Confirm:
- One track/channel per part (drums, bass, chords, [log drum], melody).
- Pitches, note timing, and project tempo match the in-app MIDI preview.

- [ ] **Step 4: Record results**

Note any discrepancy (tempo, channel split, pitch offset) as a follow-up. If all match, the seamless one-drag path is accepted.

---

## Self-Review

**Spec coverage:**
- 0.1 genre song generation -> Task 1. 0.2 concurrency -> Task 3. 0.3 interrupted recovery -> Task 3. 0.4 resilient events -> Task 2. 0.5 atomic writes -> Task 2. 0.6 lifespan + docs -> Task 3 (lifespan) + Task 4 (docs). 1.1 SMF writer -> Task 5. 1.2 endpoints -> Task 6. 1.3 frontend -> Task 7. 1.4 live acceptance -> Task 8. All spec sections covered.

**Placeholder scan:** No TBD/TODO; every code step includes complete code.

**Type consistency:** `genre_family`, `_arrangement(bars, roles)`, `_generate_generic_song(family, ...)`, `_atomic_write_text(path, text)`, `song_to_midi(draft)` / `payload_to_midi(payload)`, `PPQ = 96`, endpoints `export_song_midi` / `export_payload_midi`, frontend `exportSongMidi` / `exportPayloadMidi`, and the exported `SongDraftPanel` props (`onExportSong`, `onExportPart`) are used consistently across tasks and tests.

**Test counts are cumulative guidance:** start from the current 68 backend tests; the running totals (70 -> 72 -> 74 -> 76 -> 79) assume each prior task landed. If the baseline differs, trust "all pass" over the exact number.
