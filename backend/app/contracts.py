from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

ClearMode = Literal["none", "selected", "all"]
PayloadStatus = Literal["draft", "approved", "applied", "rejected"]
PartRole = Literal["drums", "bass", "chords", "log_drum", "melody"]
MixTarget = Literal["drums", "bass", "chords", "log_drum", "melody", "master"]
BridgeStatus = Literal["connected", "disconnected", "error"]
BridgeSetupStatus = Literal["ready", "needs_action", "error"]
BridgeSetupCheckStatus = Literal["ready", "missing", "manual", "error"]


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class Note:
    pitch: int
    startBeats: float
    durationBeats: float
    velocity: float = 0.82
    color: int = 0
    pan: float = 0.5
    slide: bool = False
    porta: bool = False
    muted: bool = False

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Note":
        note = cls(
            pitch=int(value["pitch"]),
            startBeats=float(value["startBeats"]),
            durationBeats=float(value["durationBeats"]),
            velocity=float(value.get("velocity", 0.82)),
            color=int(value.get("color", 0)),
            pan=float(value.get("pan", 0.5)),
            slide=bool(value.get("slide", False)),
            porta=bool(value.get("porta", False)),
            muted=bool(value.get("muted", False)),
        )
        note.validate()
        return note

    def validate(self) -> None:
        if not 0 <= self.pitch <= 127:
            raise ContractError(f"pitch must be 0-127, got {self.pitch}")
        if self.startBeats < 0:
            raise ContractError("startBeats must be >= 0")
        if self.durationBeats <= 0:
            raise ContractError("durationBeats must be > 0")
        if not 0 <= self.velocity <= 1:
            raise ContractError("velocity must be 0-1")
        if not 0 <= self.color <= 15:
            raise ContractError("color must be 0-15")
        if not 0 <= self.pan <= 1:
            raise ContractError("pan must be 0-1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "pitch": self.pitch,
            "startBeats": round(self.startBeats, 4),
            "durationBeats": round(self.durationBeats, 4),
            "velocity": round(self.velocity, 4),
            "color": self.color,
            "pan": round(self.pan, 4),
            "slide": self.slide,
            "porta": self.porta,
            "muted": self.muted,
        }


@dataclass(frozen=True)
class NotePayload:
    id: str
    title: str
    sourcePrompt: str
    genre: str
    bpm: int
    key: str
    scale: str
    bars: int
    target: str
    clearMode: ClearMode
    status: PayloadStatus
    createdAt: str
    notes: list[Note]
    applyInstructions: str

    @classmethod
    def create(
        cls,
        *,
        title: str,
        sourcePrompt: str,
        genre: str,
        bpm: int,
        key: str,
        scale: str,
        bars: int,
        notes: list[Note],
        clearMode: ClearMode = "none",
        target: str = "current_piano_roll",
    ) -> "NotePayload":
        payload = cls(
            id=str(uuid4()),
            title=title,
            sourcePrompt=sourcePrompt,
            genre=genre,
            bpm=bpm,
            key=key,
            scale=scale,
            bars=bars,
            target=target,
            clearMode=clearMode,
            status="draft",
            createdAt=datetime.now(UTC).isoformat(),
            notes=notes,
            applyInstructions=(
                "Open the target instrument's Piano Roll with F7, then run "
                "Tools > Scripts > FL Connector Apply Payload."
            ),
        )
        payload.validate()
        return payload

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "NotePayload":
        payload = cls(
            id=str(value["id"]),
            title=str(value["title"]),
            sourcePrompt=str(value["sourcePrompt"]),
            genre=str(value.get("genre", "Amapiano")),
            bpm=int(value["bpm"]),
            key=str(value["key"]),
            scale=str(value.get("scale", "minor")),
            bars=int(value.get("bars", 4)),
            target=str(value.get("target", "current_piano_roll")),
            clearMode=value.get("clearMode", "none"),
            status=value.get("status", "draft"),
            createdAt=str(value.get("createdAt", datetime.now(UTC).isoformat())),
            notes=[Note.from_dict(note) for note in value.get("notes", [])],
            applyInstructions=str(value.get("applyInstructions", "")),
        )
        payload.validate()
        return payload

    def validate(self) -> None:
        if self.target != "current_piano_roll":
            raise ContractError("only current_piano_roll target is supported")
        if self.clearMode not in {"none", "selected", "all"}:
            raise ContractError("clearMode must be none, selected, or all")
        if self.status not in {"draft", "approved", "applied", "rejected"}:
            raise ContractError("status is invalid")
        if not 40 <= self.bpm <= 240:
            raise ContractError("bpm must be 40-240")
        if not 1 <= self.bars <= 32:
            raise ContractError("bars must be 1-32")
        if not self.notes:
            raise ContractError("payload must include at least one note")
        max_beat = self.bars * 4
        for note in self.notes:
            note.validate()
            if note.startBeats + note.durationBeats > max_beat + 0.001:
                raise ContractError("note exceeds payload bar length")

    def with_status(self, status: PayloadStatus) -> "NotePayload":
        return NotePayload(
            id=self.id,
            title=self.title,
            sourcePrompt=self.sourcePrompt,
            genre=self.genre,
            bpm=self.bpm,
            key=self.key,
            scale=self.scale,
            bars=self.bars,
            target=self.target,
            clearMode=self.clearMode,
            status=status,
            createdAt=self.createdAt,
            notes=self.notes,
            applyInstructions=self.applyInstructions,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "sourcePrompt": self.sourcePrompt,
            "genre": self.genre,
            "bpm": self.bpm,
            "key": self.key,
            "scale": self.scale,
            "bars": self.bars,
            "target": self.target,
            "clearMode": self.clearMode,
            "status": self.status,
            "createdAt": self.createdAt,
            "notes": [note.to_dict() for note in self.notes],
            "applyInstructions": self.applyInstructions,
        }


def validate_payload_dict(value: dict[str, Any]) -> dict[str, Any]:
    return NotePayload.from_dict(value).to_dict()


@dataclass(frozen=True)
class ArrangementSection:
    name: str
    startBar: int
    bars: int
    activeParts: list[PartRole]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ArrangementSection":
        section = cls(
            name=str(value["name"]),
            startBar=int(value["startBar"]),
            bars=int(value["bars"]),
            activeParts=list(value.get("activeParts", [])),
        )
        section.validate()
        return section

    def validate(self) -> None:
        if self.startBar < 1:
            raise ContractError("arrangement startBar must be >= 1")
        if self.bars < 1:
            raise ContractError("arrangement bars must be >= 1")
        if not self.activeParts:
            raise ContractError("arrangement section must include active parts")
        invalid = set(self.activeParts) - {"drums", "bass", "chords", "log_drum", "melody"}
        if invalid:
            raise ContractError(f"arrangement section has invalid parts: {sorted(invalid)}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "startBar": self.startBar,
            "bars": self.bars,
            "activeParts": self.activeParts,
        }


@dataclass(frozen=True)
class SongPart:
    id: str
    role: PartRole
    patternName: str
    pluginHint: str
    applyOrder: int
    payload: NotePayload

    @classmethod
    def create(
        cls,
        *,
        role: PartRole,
        patternName: str,
        pluginHint: str,
        applyOrder: int,
        payload: NotePayload,
    ) -> "SongPart":
        part = cls(
            id=str(uuid4()),
            role=role,
            patternName=patternName,
            pluginHint=pluginHint,
            applyOrder=applyOrder,
            payload=payload,
        )
        part.validate()
        return part

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SongPart":
        part = cls(
            id=str(value["id"]),
            role=value["role"],
            patternName=str(value["patternName"]),
            pluginHint=str(value["pluginHint"]),
            applyOrder=int(value["applyOrder"]),
            payload=NotePayload.from_dict(value["payload"]),
        )
        part.validate()
        return part

    def validate(self) -> None:
        if self.role not in {"drums", "bass", "chords", "log_drum", "melody"}:
            raise ContractError("song part role is invalid")
        if self.applyOrder < 1:
            raise ContractError("song part applyOrder must be >= 1")
        self.payload.validate()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "patternName": self.patternName,
            "pluginHint": self.pluginHint,
            "applyOrder": self.applyOrder,
            "payload": self.payload.to_dict(),
        }


@dataclass(frozen=True)
class SongDraft:
    id: str
    title: str
    sourcePrompt: str
    genre: str
    bpm: int
    key: str
    scale: str
    bars: int
    status: PayloadStatus
    createdAt: str
    parts: list[SongPart]
    arrangement: list[ArrangementSection]

    @classmethod
    def create(
        cls,
        *,
        title: str,
        sourcePrompt: str,
        genre: str,
        bpm: int,
        key: str,
        scale: str,
        bars: int,
        parts: list[SongPart],
        arrangement: list[ArrangementSection],
    ) -> "SongDraft":
        draft = cls(
            id=str(uuid4()),
            title=title,
            sourcePrompt=sourcePrompt,
            genre=genre,
            bpm=bpm,
            key=key,
            scale=scale,
            bars=bars,
            status="draft",
            createdAt=datetime.now(UTC).isoformat(),
            parts=parts,
            arrangement=arrangement,
        )
        draft.validate()
        return draft

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SongDraft":
        draft = cls(
            id=str(value["id"]),
            title=str(value["title"]),
            sourcePrompt=str(value["sourcePrompt"]),
            genre=str(value["genre"]),
            bpm=int(value["bpm"]),
            key=str(value["key"]),
            scale=str(value["scale"]),
            bars=int(value["bars"]),
            status=value.get("status", "draft"),
            createdAt=str(value.get("createdAt", datetime.now(UTC).isoformat())),
            parts=[SongPart.from_dict(part) for part in value.get("parts", [])],
            arrangement=[
                ArrangementSection.from_dict(section)
                for section in value.get("arrangement", [])
            ],
        )
        draft.validate()
        return draft

    def validate(self) -> None:
        if self.status not in {"draft", "approved", "applied", "rejected"}:
            raise ContractError("song draft status is invalid")
        if not 40 <= self.bpm <= 240:
            raise ContractError("song draft bpm must be 40-240")
        if not 1 <= self.bars <= 32:
            raise ContractError("song draft bars must be 1-32")
        if not self.parts:
            raise ContractError("song draft must include at least one part")
        if not self.arrangement:
            raise ContractError("song draft must include arrangement sections")
        for part in self.parts:
            part.validate()
            if part.payload.bpm != self.bpm or part.payload.key != self.key:
                raise ContractError("song part tempo/key must match song draft")
            if part.payload.bars != self.bars:
                raise ContractError("song part bars must match song draft")
        for section in self.arrangement:
            section.validate()
            if section.startBar + section.bars - 1 > self.bars:
                raise ContractError("arrangement section exceeds song length")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "sourcePrompt": self.sourcePrompt,
            "genre": self.genre,
            "bpm": self.bpm,
            "key": self.key,
            "scale": self.scale,
            "bars": self.bars,
            "status": self.status,
            "createdAt": self.createdAt,
            "parts": [part.to_dict() for part in self.parts],
            "arrangement": [section.to_dict() for section in self.arrangement],
        }


@dataclass(frozen=True)
class MixStep:
    order: int
    target: MixTarget
    plugin: str
    slot: int
    action: str
    settings: dict[str, str]
    clickPath: str
    reason: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MixStep":
        step = cls(
            order=int(value["order"]),
            target=value["target"],
            plugin=str(value["plugin"]),
            slot=int(value["slot"]),
            action=str(value["action"]),
            settings={str(k): str(v) for k, v in value.get("settings", {}).items()},
            clickPath=str(value["clickPath"]),
            reason=str(value["reason"]),
        )
        step.validate()
        return step

    def validate(self) -> None:
        if self.order < 1:
            raise ContractError("mix step order must be >= 1")
        if self.target not in {"drums", "bass", "chords", "log_drum", "melody", "master"}:
            raise ContractError("mix step target is invalid")
        if not 1 <= self.slot <= 10:
            raise ContractError("mix step slot must be 1-10")
        if not self.plugin:
            raise ContractError("mix step plugin is required")
        if not self.action:
            raise ContractError("mix step action is required")
        if not self.clickPath:
            raise ContractError("mix step clickPath is required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "target": self.target,
            "plugin": self.plugin,
            "slot": self.slot,
            "action": self.action,
            "settings": self.settings,
            "clickPath": self.clickPath,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class MasteringPlan:
    id: str
    title: str
    sourcePrompt: str
    genre: str
    bpm: int
    targetLoudness: str
    status: PayloadStatus
    createdAt: str
    steps: list[MixStep]
    safetyNotes: list[str]

    @classmethod
    def create(
        cls,
        *,
        title: str,
        sourcePrompt: str,
        genre: str,
        bpm: int,
        targetLoudness: str,
        steps: list[MixStep],
        safetyNotes: list[str],
    ) -> "MasteringPlan":
        plan = cls(
            id=str(uuid4()),
            title=title,
            sourcePrompt=sourcePrompt,
            genre=genre,
            bpm=bpm,
            targetLoudness=targetLoudness,
            status="draft",
            createdAt=datetime.now(UTC).isoformat(),
            steps=steps,
            safetyNotes=safetyNotes,
        )
        plan.validate()
        return plan

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MasteringPlan":
        plan = cls(
            id=str(value["id"]),
            title=str(value["title"]),
            sourcePrompt=str(value["sourcePrompt"]),
            genre=str(value["genre"]),
            bpm=int(value["bpm"]),
            targetLoudness=str(value["targetLoudness"]),
            status=value.get("status", "draft"),
            createdAt=str(value.get("createdAt", datetime.now(UTC).isoformat())),
            steps=[MixStep.from_dict(step) for step in value.get("steps", [])],
            safetyNotes=[str(note) for note in value.get("safetyNotes", [])],
        )
        plan.validate()
        return plan

    def validate(self) -> None:
        if self.status not in {"draft", "approved", "applied", "rejected"}:
            raise ContractError("mastering plan status is invalid")
        if not 40 <= self.bpm <= 240:
            raise ContractError("mastering plan bpm must be 40-240")
        if not self.steps:
            raise ContractError("mastering plan must include steps")
        orders = [step.order for step in self.steps]
        if len(orders) != len(set(orders)):
            raise ContractError("mastering plan step orders must be unique")
        for step in self.steps:
            step.validate()
        if not any(step.target == "master" for step in self.steps):
            raise ContractError("mastering plan must include master chain steps")

    def with_status(self, status: PayloadStatus) -> "MasteringPlan":
        return MasteringPlan(
            id=self.id,
            title=self.title,
            sourcePrompt=self.sourcePrompt,
            genre=self.genre,
            bpm=self.bpm,
            targetLoudness=self.targetLoudness,
            status=status,
            createdAt=self.createdAt,
            steps=self.steps,
            safetyNotes=self.safetyNotes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "sourcePrompt": self.sourcePrompt,
            "genre": self.genre,
            "bpm": self.bpm,
            "targetLoudness": self.targetLoudness,
            "status": self.status,
            "createdAt": self.createdAt,
            "steps": [step.to_dict() for step in self.steps],
            "safetyNotes": self.safetyNotes,
        }


@dataclass(frozen=True)
class BridgeTransportSnapshot:
    playing: bool
    recording: bool
    loopMode: int
    songPosition: float
    songPositionHint: str
    songLengthBars: int | None
    tempo: float | None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BridgeTransportSnapshot":
        song_length = value.get("songLengthBars")
        tempo = value.get("tempo")
        snapshot = cls(
            playing=bool(value.get("playing", False)),
            recording=bool(value.get("recording", False)),
            loopMode=int(value.get("loopMode", 0)),
            songPosition=float(value.get("songPosition", 0)),
            songPositionHint=str(value.get("songPositionHint", "")),
            songLengthBars=int(song_length) if song_length is not None else None,
            tempo=float(tempo) if tempo is not None else None,
        )
        snapshot.validate()
        return snapshot

    def validate(self) -> None:
        if self.loopMode not in {0, 1}:
            raise ContractError("bridge loopMode must be 0 or 1")
        if self.songPosition < 0:
            raise ContractError("bridge songPosition must be >= 0")
        if self.songLengthBars is not None and self.songLengthBars < 0:
            raise ContractError("bridge songLengthBars must be >= 0")
        if self.tempo is not None and not 40 <= self.tempo <= 240:
            raise ContractError("bridge tempo must be 40-240")

    def to_dict(self) -> dict[str, Any]:
        return {
            "playing": self.playing,
            "recording": self.recording,
            "loopMode": self.loopMode,
            "songPosition": round(self.songPosition, 4),
            "songPositionHint": self.songPositionHint,
            "songLengthBars": self.songLengthBars,
            "tempo": round(self.tempo, 4) if self.tempo is not None else None,
        }


@dataclass(frozen=True)
class BridgeMixerTrack:
    index: int
    name: str
    volume: float | None
    pan: float | None
    selected: bool
    slots: list[str]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BridgeMixerTrack":
        volume = value.get("volume")
        pan = value.get("pan")
        track = cls(
            index=int(value["index"]),
            name=str(value.get("name", "")),
            volume=float(volume) if volume is not None else None,
            pan=float(pan) if pan is not None else None,
            selected=bool(value.get("selected", False)),
            slots=[str(slot) for slot in value.get("slots", [])],
        )
        track.validate()
        return track

    def validate(self) -> None:
        if self.index < 0:
            raise ContractError("bridge mixer track index must be >= 0")
        if self.volume is not None and not 0 <= self.volume <= 1:
            raise ContractError("bridge mixer track volume must be 0-1")
        if self.pan is not None and not -1 <= self.pan <= 1:
            raise ContractError("bridge mixer track pan must be -1 to 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "volume": round(self.volume, 4) if self.volume is not None else None,
            "pan": round(self.pan, 4) if self.pan is not None else None,
            "selected": self.selected,
            "slots": self.slots,
        }


@dataclass(frozen=True)
class BridgeSnapshot:
    status: BridgeStatus
    message: str
    source: str
    createdAt: str
    flVersion: str | None
    projectTitle: str | None
    selectedTrack: int | None
    trackCount: int | None
    transport: BridgeTransportSnapshot | None
    tracks: list[BridgeMixerTrack]
    setup: list[str]
    errors: list[str]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BridgeSnapshot":
        selected_track = value.get("selectedTrack")
        track_count = value.get("trackCount")
        transport = value.get("transport")
        snapshot = cls(
            status=value.get("status", "disconnected"),
            message=str(value.get("message", "")),
            source=str(value.get("source", "flapi")),
            createdAt=str(value.get("createdAt", datetime.now(UTC).isoformat())),
            flVersion=str(value["flVersion"]) if value.get("flVersion") is not None else None,
            projectTitle=str(value["projectTitle"]) if value.get("projectTitle") is not None else None,
            selectedTrack=int(selected_track) if selected_track is not None else None,
            trackCount=int(track_count) if track_count is not None else None,
            transport=BridgeTransportSnapshot.from_dict(transport) if transport else None,
            tracks=[BridgeMixerTrack.from_dict(track) for track in value.get("tracks", [])],
            setup=[str(step) for step in value.get("setup", [])],
            errors=[str(error) for error in value.get("errors", [])],
        )
        snapshot.validate()
        return snapshot

    def validate(self) -> None:
        if self.status not in {"connected", "disconnected", "error"}:
            raise ContractError("bridge status is invalid")
        if not self.message:
            raise ContractError("bridge message is required")
        if self.selectedTrack is not None and self.selectedTrack < 0:
            raise ContractError("bridge selectedTrack must be >= 0")
        if self.trackCount is not None and self.trackCount < 0:
            raise ContractError("bridge trackCount must be >= 0")
        if self.status == "connected" and self.transport is None:
            raise ContractError("connected bridge snapshots require transport")
        for track in self.tracks:
            track.validate()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "source": self.source,
            "createdAt": self.createdAt,
            "flVersion": self.flVersion,
            "projectTitle": self.projectTitle,
            "selectedTrack": self.selectedTrack,
            "trackCount": self.trackCount,
            "transport": self.transport.to_dict() if self.transport else None,
            "tracks": [track.to_dict() for track in self.tracks],
            "setup": self.setup,
            "errors": self.errors,
        }


@dataclass(frozen=True)
class BridgeSetupCheck:
    key: str
    label: str
    status: BridgeSetupCheckStatus
    detail: str
    action: str
    blocking: bool = True

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BridgeSetupCheck":
        check = cls(
            key=str(value["key"]),
            label=str(value["label"]),
            status=value.get("status", "missing"),
            detail=str(value.get("detail", "")),
            action=str(value.get("action", "")),
            blocking=bool(value.get("blocking", True)),
        )
        check.validate()
        return check

    def validate(self) -> None:
        if not self.key:
            raise ContractError("bridge setup check key is required")
        if not self.label:
            raise ContractError("bridge setup check label is required")
        if self.status not in {"ready", "missing", "manual", "error"}:
            raise ContractError("bridge setup check status is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "detail": self.detail,
            "action": self.action,
            "blocking": self.blocking,
        }


@dataclass(frozen=True)
class BridgeSetupPlan:
    status: BridgeSetupStatus
    message: str
    canInstallScripts: bool
    installCommand: str | None
    manualSteps: list[str]
    checks: list[BridgeSetupCheck]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BridgeSetupPlan":
        install_command = value.get("installCommand")
        plan = cls(
            status=value.get("status", "needs_action"),
            message=str(value.get("message", "")),
            canInstallScripts=bool(value.get("canInstallScripts", False)),
            installCommand=str(install_command) if install_command is not None else None,
            manualSteps=[str(step) for step in value.get("manualSteps", [])],
            checks=[BridgeSetupCheck.from_dict(check) for check in value.get("checks", [])],
        )
        plan.validate()
        return plan

    def validate(self) -> None:
        if self.status not in {"ready", "needs_action", "error"}:
            raise ContractError("bridge setup status is invalid")
        if not self.message:
            raise ContractError("bridge setup message is required")
        if not self.checks:
            raise ContractError("bridge setup plan must include checks")
        if self.canInstallScripts and not self.installCommand:
            raise ContractError("bridge setup installCommand is required when install is available")
        for check in self.checks:
            check.validate()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "canInstallScripts": self.canInstallScripts,
            "installCommand": self.installCommand,
            "manualSteps": self.manualSteps,
            "checks": [check.to_dict() for check in self.checks],
        }
