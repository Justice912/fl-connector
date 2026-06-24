from __future__ import annotations

import json
import os
from pathlib import Path

from .contracts import MasteringPlan, NotePayload, SongDraft


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


class PayloadStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.drafts_dir = base_dir / "drafts"
        self.songs_dir = base_dir / "songs"
        self.mastering_dir = base_dir / "mastering"
        self.events_path = base_dir / "events.jsonl"
        self.current_path = base_dir / "current_payload.json"
        self.current_song_path = base_dir / "current_song.json"
        self.current_mastering_path = base_dir / "current_mastering.json"

    def ensure(self) -> None:
        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        self.songs_dir.mkdir(parents=True, exist_ok=True)
        self.mastering_dir.mkdir(parents=True, exist_ok=True)

    def save_draft(self, payload: NotePayload) -> NotePayload:
        self.ensure()
        path = self.drafts_dir / f"{payload.id}.json"
        _atomic_write_text(path, json.dumps(payload.to_dict(), indent=2))
        self.event("generated", f"Generated {payload.title}", payload.id)
        return payload

    def get(self, payload_id: str) -> NotePayload:
        path = self.drafts_dir / f"{payload_id}.json"
        if not path.exists():
            raise FileNotFoundError(payload_id)
        return NotePayload.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def approve(self, payload_id: str, fl_payload_path: Path) -> NotePayload:
        payload = self.get(payload_id).with_status("approved")
        self.ensure()
        payload_json = json.dumps(payload.to_dict(), indent=2)
        _atomic_write_text(fl_payload_path, payload_json)
        _atomic_write_text(self.drafts_dir / f"{payload.id}.json", payload_json)
        _atomic_write_text(self.current_path, payload_json)
        self.event("approved", "Approved payload and wrote FL apply file", payload.id)
        return payload

    def current(self) -> NotePayload | None:
        if not self.current_path.exists():
            return None
        return NotePayload.from_dict(json.loads(self.current_path.read_text(encoding="utf-8")))

    def save_song_draft(self, draft: SongDraft) -> SongDraft:
        self.ensure()
        for part in draft.parts:
            self.save_draft(part.payload)
        draft_json = json.dumps(draft.to_dict(), indent=2)
        _atomic_write_text(self.songs_dir / f"{draft.id}.json", draft_json)
        _atomic_write_text(self.current_song_path, draft_json)
        self.event("song", f"Generated {draft.title} with {len(draft.parts)} parts", draft.id)
        return draft

    def get_song(self, song_id: str) -> SongDraft:
        path = self.songs_dir / f"{song_id}.json"
        if not path.exists():
            raise FileNotFoundError(song_id)
        return SongDraft.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def current_song(self) -> SongDraft | None:
        if not self.current_song_path.exists():
            return None
        return SongDraft.from_dict(json.loads(self.current_song_path.read_text(encoding="utf-8")))

    def save_mastering_plan(self, plan: MasteringPlan) -> MasteringPlan:
        self.ensure()
        plan_json = json.dumps(plan.to_dict(), indent=2)
        _atomic_write_text(self.mastering_dir / f"{plan.id}.json", plan_json)
        _atomic_write_text(self.current_mastering_path, plan_json)
        self.event("mastering", f"Generated {plan.title} with {len(plan.steps)} steps", plan.id)
        return plan

    def get_mastering_plan(self, plan_id: str) -> MasteringPlan:
        path = self.mastering_dir / f"{plan_id}.json"
        if not path.exists():
            raise FileNotFoundError(plan_id)
        return MasteringPlan.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def approve_mastering_plan(self, plan_id: str, fl_plan_path: Path) -> MasteringPlan:
        plan = self.get_mastering_plan(plan_id).with_status("approved")
        self.ensure()
        plan_json = json.dumps(plan.to_dict(), indent=2)
        _atomic_write_text(fl_plan_path, plan_json)
        _atomic_write_text(self.mastering_dir / f"{plan.id}.json", plan_json)
        _atomic_write_text(self.current_mastering_path, plan_json)
        self.event("mastering-approved", "Approved mastering plan and wrote FL connector file", plan.id)
        return plan

    def current_mastering_plan(self) -> MasteringPlan | None:
        if not self.current_mastering_path.exists():
            return None
        return MasteringPlan.from_dict(json.loads(self.current_mastering_path.read_text(encoding="utf-8")))

    def event(self, kind: str, message: str, payload_id: str | None = None) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        item = {"kind": kind, "message": message, "payloadId": payload_id}
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item) + "\n")

    def events(self, limit: int = 50) -> list[dict[str, object]]:
        if not self.events_path.exists():
            return []
        rows: list[dict[str, object]] = []
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
        return rows[-limit:]
