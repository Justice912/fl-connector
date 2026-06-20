from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from .contracts import NotePayload

ProjectStatus = Literal[
    "draft",
    "uploaded",
    "queued",
    "analyzing",
    "review",
    "approved",
    "building",
    "complete",
    "error",
]
JobStatus = Literal["queued", "running", "complete", "interrupted", "error", "cancelled"]
StemRole = Literal[
    "drums",
    "percussion",
    "bass",
    "chords",
    "log_drum",
    "melody",
    "vocals",
    "guitar",
    "fx",
    "other",
]
OutputMode = Literal["midi", "audio"]

PROJECT_STATUSES = {
    "draft",
    "uploaded",
    "queued",
    "analyzing",
    "review",
    "approved",
    "building",
    "complete",
    "error",
}
JOB_STATUSES = {"queued", "running", "complete", "interrupted", "error", "cancelled"}
STEM_ROLES = {
    "drums",
    "percussion",
    "bass",
    "chords",
    "log_drum",
    "melody",
    "vocals",
    "guitar",
    "fx",
    "other",
}


class ReconstructionError(ValueError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _confidence(value: float, label: str) -> float:
    number = float(value)
    if not 0 <= number <= 1:
        raise ReconstructionError(f"{label} must be between 0 and 1")
    return number


@dataclass(frozen=True)
class StemAsset:
    id: str
    fileName: str
    storedName: str
    relativePath: str
    mediaType: str
    sizeBytes: int
    sha256: str
    role: StemRole
    status: str
    createdAt: str
    durationSeconds: float | None = None
    sampleRate: int | None = None

    @classmethod
    def create(
        cls,
        *,
        fileName: str,
        storedName: str,
        relativePath: str,
        mediaType: str,
        sizeBytes: int,
        sha256: str,
        role: StemRole = "other",
    ) -> "StemAsset":
        stem = cls(
            id=str(uuid4()),
            fileName=fileName,
            storedName=storedName,
            relativePath=relativePath,
            mediaType=mediaType,
            sizeBytes=int(sizeBytes),
            sha256=sha256,
            role=role,
            status="uploaded",
            createdAt=_now(),
        )
        stem.validate()
        return stem

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "StemAsset":
        stem = cls(
            id=str(value["id"]),
            fileName=str(value["fileName"]),
            storedName=str(value["storedName"]),
            relativePath=str(value["relativePath"]),
            mediaType=str(value["mediaType"]),
            sizeBytes=int(value["sizeBytes"]),
            sha256=str(value["sha256"]),
            role=value.get("role", "other"),
            status=str(value.get("status", "uploaded")),
            createdAt=str(value.get("createdAt", _now())),
            durationSeconds=(
                float(value["durationSeconds"])
                if value.get("durationSeconds") is not None
                else None
            ),
            sampleRate=(int(value["sampleRate"]) if value.get("sampleRate") is not None else None),
        )
        stem.validate()
        return stem

    def validate(self) -> None:
        if not self.fileName or not self.storedName:
            raise ReconstructionError("stem file names are required")
        if self.sizeBytes <= 0:
            raise ReconstructionError("stem size must be greater than zero")
        if len(self.sha256) != 64:
            raise ReconstructionError("stem sha256 must contain 64 characters")
        if self.role not in STEM_ROLES:
            raise ReconstructionError("stem role is invalid")
        if self.durationSeconds is not None and self.durationSeconds <= 0:
            raise ReconstructionError("stem duration must be greater than zero")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "fileName": self.fileName,
            "storedName": self.storedName,
            "relativePath": self.relativePath,
            "mediaType": self.mediaType,
            "sizeBytes": self.sizeBytes,
            "sha256": self.sha256,
            "role": self.role,
            "status": self.status,
            "createdAt": self.createdAt,
            "durationSeconds": self.durationSeconds,
            "sampleRate": self.sampleRate,
        }


@dataclass(frozen=True)
class AnalysisJob:
    id: str
    status: JobStatus
    progress: int
    stage: str
    message: str
    attempt: int
    createdAt: str
    updatedAt: str
    error: str | None = None

    @classmethod
    def create(cls, attempt: int = 1) -> "AnalysisJob":
        now = _now()
        return cls(
            id=str(uuid4()),
            status="queued",
            progress=0,
            stage="queued",
            message="Waiting for local analysis.",
            attempt=attempt,
            createdAt=now,
            updatedAt=now,
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AnalysisJob":
        job = cls(
            id=str(value["id"]),
            status=value.get("status", "queued"),
            progress=int(value.get("progress", 0)),
            stage=str(value.get("stage", "queued")),
            message=str(value.get("message", "")),
            attempt=int(value.get("attempt", 1)),
            createdAt=str(value.get("createdAt", _now())),
            updatedAt=str(value.get("updatedAt", _now())),
            error=(str(value["error"]) if value.get("error") else None),
        )
        job.validate()
        return job

    def validate(self) -> None:
        if self.status not in JOB_STATUSES:
            raise ReconstructionError("analysis job status is invalid")
        if not 0 <= self.progress <= 100:
            raise ReconstructionError("analysis progress must be 0-100")
        if self.attempt < 1:
            raise ReconstructionError("analysis attempt must be positive")

    def with_progress(
        self,
        *,
        status: JobStatus | None = None,
        progress: int | None = None,
        stage: str | None = None,
        message: str | None = None,
        error: str | None = None,
    ) -> "AnalysisJob":
        updated = replace(
            self,
            status=status or self.status,
            progress=self.progress if progress is None else progress,
            stage=stage or self.stage,
            message=self.message if message is None else message,
            error=error,
            updatedAt=_now(),
        )
        updated.validate()
        return updated

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "progress": self.progress,
            "stage": self.stage,
            "message": self.message,
            "attempt": self.attempt,
            "createdAt": self.createdAt,
            "updatedAt": self.updatedAt,
            "error": self.error,
        }


@dataclass(frozen=True)
class TimelineSection:
    id: str
    name: str
    startSeconds: float
    endSeconds: float
    startBar: int
    bars: int
    activePartIds: list[str]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TimelineSection":
        section = cls(
            id=str(value.get("id", uuid4())),
            name=str(value["name"]),
            startSeconds=float(value["startSeconds"]),
            endSeconds=float(value["endSeconds"]),
            startBar=int(value["startBar"]),
            bars=int(value["bars"]),
            activePartIds=[str(item) for item in value.get("activePartIds", [])],
        )
        section.validate()
        return section

    def validate(self) -> None:
        if self.startSeconds < 0 or self.endSeconds <= self.startSeconds:
            raise ReconstructionError("timeline section seconds are invalid")
        if self.startBar < 1 or self.bars < 1:
            raise ReconstructionError("timeline section bars are invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "startSeconds": self.startSeconds,
            "endSeconds": self.endSeconds,
            "startBar": self.startBar,
            "bars": self.bars,
            "activePartIds": self.activePartIds,
        }


@dataclass(frozen=True)
class PatternSlice:
    id: str
    name: str
    startBar: int
    bars: int
    payload: NotePayload
    placements: list[int]

    @classmethod
    def create(
        cls,
        *,
        name: str,
        startBar: int,
        payload: NotePayload,
        bars: int | None = None,
        placements: list[int] | None = None,
    ) -> "PatternSlice":
        pattern = cls(
            id=str(uuid4()),
            name=name,
            startBar=int(startBar),
            bars=int(bars if bars is not None else payload.bars),
            payload=payload,
            placements=list(placements or [startBar]),
        )
        pattern.validate()
        return pattern

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PatternSlice":
        pattern = cls(
            id=str(value["id"]),
            name=str(value["name"]),
            startBar=int(value["startBar"]),
            bars=int(value["bars"]),
            payload=NotePayload.from_dict(value["payload"]),
            placements=[int(item) for item in value.get("placements", [value["startBar"]])],
        )
        pattern.validate()
        return pattern

    def validate(self) -> None:
        if self.startBar < 1:
            raise ReconstructionError("pattern start bar must be positive")
        if not 1 <= self.bars <= 32:
            raise ReconstructionError("pattern slices must be 1-32 bars")
        if self.payload.bars != self.bars:
            raise ReconstructionError("pattern bars must match payload bars")
        if not self.placements or any(bar < 1 for bar in self.placements):
            raise ReconstructionError("pattern placements must contain positive bars")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "startBar": self.startBar,
            "bars": self.bars,
            "payload": self.payload.to_dict(),
            "placements": self.placements,
        }


@dataclass(frozen=True)
class SoundMatch:
    id: str
    name: str
    kind: str
    installed: bool
    source: str
    score: float
    reason: str
    path: str | None = None
    url: str | None = None
    licenseName: str | None = None
    licenseUrl: str | None = None
    priceClass: str = "installed"
    platform: str = "Windows"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SoundMatch":
        match = cls(
            id=str(value.get("id", uuid4())),
            name=str(value["name"]),
            kind=str(value.get("kind", "plugin")),
            installed=bool(value.get("installed", False)),
            source=str(value.get("source", "inventory")),
            score=_confidence(float(value.get("score", 0)), "sound score"),
            reason=str(value.get("reason", "")),
            path=(str(value["path"]) if value.get("path") else None),
            url=(str(value["url"]) if value.get("url") else None),
            licenseName=(str(value["licenseName"]) if value.get("licenseName") else None),
            licenseUrl=(str(value["licenseUrl"]) if value.get("licenseUrl") else None),
            priceClass=str(value.get("priceClass", "installed")),
            platform=str(value.get("platform", "Windows")),
        )
        if not match.installed and (not match.url or not match.licenseUrl):
            raise ReconstructionError("download recommendations require URL and license URL")
        return match

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "installed": self.installed,
            "source": self.source,
            "score": self.score,
            "reason": self.reason,
            "path": self.path,
            "url": self.url,
            "licenseName": self.licenseName,
            "licenseUrl": self.licenseUrl,
            "priceClass": self.priceClass,
            "platform": self.platform,
        }


@dataclass(frozen=True)
class ReconstructedPart:
    id: str
    sourceStemId: str
    name: str
    role: StemRole
    outputMode: OutputMode
    confidence: float
    requiresReview: bool
    instrumentHint: str
    patterns: list[PatternSlice]
    audioRelativePath: str | None
    audioStartSeconds: float
    selectedSoundId: str | None
    warnings: list[str]
    approved: bool

    @classmethod
    def create(
        cls,
        *,
        sourceStemId: str,
        name: str,
        role: StemRole,
        outputMode: OutputMode,
        confidence: float,
        patterns: list[PatternSlice] | None = None,
        audioRelativePath: str | None = None,
        instrumentHint: str = "",
    ) -> "ReconstructedPart":
        value = _confidence(confidence, "part confidence")
        part = cls(
            id=str(uuid4()),
            sourceStemId=sourceStemId,
            name=name,
            role=role,
            outputMode=outputMode,
            confidence=value,
            requiresReview=0.60 <= value < 0.80,
            instrumentHint=instrumentHint,
            patterns=list(patterns or []),
            audioRelativePath=audioRelativePath,
            audioStartSeconds=0.0,
            selectedSoundId=None,
            warnings=[],
            approved=False,
        )
        part.validate()
        return part

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ReconstructedPart":
        part = cls(
            id=str(value["id"]),
            sourceStemId=str(value["sourceStemId"]),
            name=str(value["name"]),
            role=value.get("role", "other"),
            outputMode=value.get("outputMode", "audio"),
            confidence=float(value.get("confidence", 0)),
            requiresReview=bool(value.get("requiresReview", False)),
            instrumentHint=str(value.get("instrumentHint", "")),
            patterns=[PatternSlice.from_dict(item) for item in value.get("patterns", [])],
            audioRelativePath=(
                str(value["audioRelativePath"]) if value.get("audioRelativePath") else None
            ),
            audioStartSeconds=float(value.get("audioStartSeconds", 0)),
            selectedSoundId=(str(value["selectedSoundId"]) if value.get("selectedSoundId") else None),
            warnings=[str(item) for item in value.get("warnings", [])],
            approved=bool(value.get("approved", False)),
        )
        part.validate()
        return part

    def validate(self) -> None:
        _confidence(self.confidence, "part confidence")
        if self.role not in STEM_ROLES:
            raise ReconstructionError("part role is invalid")
        if self.outputMode not in {"midi", "audio"}:
            raise ReconstructionError("part output mode is invalid")
        if self.outputMode == "midi" and not self.patterns:
            raise ReconstructionError("MIDI parts require at least one pattern")
        for pattern in self.patterns:
            pattern.validate()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sourceStemId": self.sourceStemId,
            "name": self.name,
            "role": self.role,
            "outputMode": self.outputMode,
            "confidence": self.confidence,
            "requiresReview": self.requiresReview,
            "instrumentHint": self.instrumentHint,
            "patterns": [item.to_dict() for item in self.patterns],
            "audioRelativePath": self.audioRelativePath,
            "audioStartSeconds": self.audioStartSeconds,
            "selectedSoundId": self.selectedSoundId,
            "warnings": self.warnings,
            "approved": self.approved,
        }


@dataclass(frozen=True)
class AnalysisSummary:
    bpm: float
    bpmConfidence: float
    key: str
    scale: str
    keyConfidence: float
    timeSignature: str
    durationSeconds: float
    integratedLoudness: float | None
    peakDb: float | None
    stereoWidth: float | None
    sections: list[TimelineSection]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AnalysisSummary":
        summary = cls(
            bpm=float(value["bpm"]),
            bpmConfidence=float(value.get("bpmConfidence", 0)),
            key=str(value.get("key", "C")),
            scale=str(value.get("scale", "minor")),
            keyConfidence=float(value.get("keyConfidence", 0)),
            timeSignature=str(value.get("timeSignature", "4/4")),
            durationSeconds=float(value.get("durationSeconds", 0)),
            integratedLoudness=(
                float(value["integratedLoudness"])
                if value.get("integratedLoudness") is not None
                else None
            ),
            peakDb=(float(value["peakDb"]) if value.get("peakDb") is not None else None),
            stereoWidth=(
                float(value["stereoWidth"])
                if value.get("stereoWidth") is not None
                else None
            ),
            sections=[TimelineSection.from_dict(item) for item in value.get("sections", [])],
        )
        if not 40 <= summary.bpm <= 240:
            raise ReconstructionError("analysis BPM must be 40-240")
        _confidence(summary.bpmConfidence, "BPM confidence")
        _confidence(summary.keyConfidence, "key confidence")
        return summary

    def to_dict(self) -> dict[str, Any]:
        return {
            "bpm": self.bpm,
            "bpmConfidence": self.bpmConfidence,
            "key": self.key,
            "scale": self.scale,
            "keyConfidence": self.keyConfidence,
            "timeSignature": self.timeSignature,
            "durationSeconds": self.durationSeconds,
            "integratedLoudness": self.integratedLoudness,
            "peakDb": self.peakDb,
            "stereoWidth": self.stereoWidth,
            "sections": [item.to_dict() for item in self.sections],
        }


@dataclass(frozen=True)
class GuideStep:
    id: str
    order: int
    title: str
    area: str
    action: str
    menuPath: str
    shortcut: str | None
    imageAsset: str
    hotspot: dict[str, float]
    expectedState: str
    completed: bool = False

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "GuideStep":
        return cls(
            id=str(value.get("id", uuid4())),
            order=int(value["order"]),
            title=str(value["title"]),
            area=str(value["area"]),
            action=str(value["action"]),
            menuPath=str(value["menuPath"]),
            shortcut=(str(value["shortcut"]) if value.get("shortcut") else None),
            imageAsset=str(value["imageAsset"]),
            hotspot={str(k): float(v) for k, v in value.get("hotspot", {}).items()},
            expectedState=str(value["expectedState"]),
            completed=bool(value.get("completed", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "order": self.order,
            "title": self.title,
            "area": self.area,
            "action": self.action,
            "menuPath": self.menuPath,
            "shortcut": self.shortcut,
            "imageAsset": self.imageAsset,
            "hotspot": self.hotspot,
            "expectedState": self.expectedState,
            "completed": self.completed,
        }


@dataclass(frozen=True)
class ReconstructionProject:
    id: str
    title: str
    genreProfile: str
    rightsAccepted: bool
    status: ProjectStatus
    createdAt: str
    updatedAt: str
    storageBytes: int
    analysisOverrides: dict[str, Any]
    stems: list[StemAsset]
    analysisJob: AnalysisJob | None
    analysisSummary: AnalysisSummary | None
    parts: list[ReconstructedPart]
    timeline: list[TimelineSection]
    soundMatches: list[SoundMatch]
    guideSteps: list[GuideStep]
    mixPlan: dict[str, Any] | None
    warnings: list[str]

    @classmethod
    def create(
        cls,
        *,
        title: str,
        rightsAccepted: bool,
        genreProfile: str = "south_african_dance",
    ) -> "ReconstructionProject":
        if not rightsAccepted:
            raise ReconstructionError("Confirm ownership or permission before creating a project")
        if not title.strip():
            raise ReconstructionError("project title is required")
        now = _now()
        return cls(
            id=str(uuid4()),
            title=title.strip(),
            genreProfile=genreProfile,
            rightsAccepted=True,
            status="draft",
            createdAt=now,
            updatedAt=now,
            storageBytes=0,
            analysisOverrides={},
            stems=[],
            analysisJob=None,
            analysisSummary=None,
            parts=[],
            timeline=[],
            soundMatches=[],
            guideSteps=[],
            mixPlan=None,
            warnings=[],
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ReconstructionProject":
        project = cls(
            id=str(value["id"]),
            title=str(value["title"]),
            genreProfile=str(value.get("genreProfile", "south_african_dance")),
            rightsAccepted=bool(value.get("rightsAccepted", False)),
            status=value.get("status", "draft"),
            createdAt=str(value.get("createdAt", _now())),
            updatedAt=str(value.get("updatedAt", _now())),
            storageBytes=int(value.get("storageBytes", 0)),
            analysisOverrides=dict(value.get("analysisOverrides", {})),
            stems=[StemAsset.from_dict(item) for item in value.get("stems", [])],
            analysisJob=(
                AnalysisJob.from_dict(value["analysisJob"])
                if value.get("analysisJob")
                else None
            ),
            analysisSummary=(
                AnalysisSummary.from_dict(value["analysisSummary"])
                if value.get("analysisSummary")
                else None
            ),
            parts=[ReconstructedPart.from_dict(item) for item in value.get("parts", [])],
            timeline=[TimelineSection.from_dict(item) for item in value.get("timeline", [])],
            soundMatches=[SoundMatch.from_dict(item) for item in value.get("soundMatches", [])],
            guideSteps=[GuideStep.from_dict(item) for item in value.get("guideSteps", [])],
            mixPlan=(dict(value["mixPlan"]) if value.get("mixPlan") else None),
            warnings=[str(item) for item in value.get("warnings", [])],
        )
        project.validate()
        return project

    def validate(self) -> None:
        if not self.rightsAccepted:
            raise ReconstructionError("project requires ownership or permission confirmation")
        if self.status not in PROJECT_STATUSES:
            raise ReconstructionError("project status is invalid")
        if self.storageBytes < 0:
            raise ReconstructionError("project storage size cannot be negative")
        if len({stem.id for stem in self.stems}) != len(self.stems):
            raise ReconstructionError("project stem IDs must be unique")
        if len({part.id for part in self.parts}) != len(self.parts):
            raise ReconstructionError("project part IDs must be unique")

    def with_changes(self, **changes: Any) -> "ReconstructionProject":
        project = replace(self, updatedAt=_now(), **changes)
        project.validate()
        return project

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "genreProfile": self.genreProfile,
            "rightsAccepted": self.rightsAccepted,
            "status": self.status,
            "createdAt": self.createdAt,
            "updatedAt": self.updatedAt,
            "storageBytes": self.storageBytes,
            "analysisOverrides": self.analysisOverrides,
            "stems": [item.to_dict() for item in self.stems],
            "analysisJob": self.analysisJob.to_dict() if self.analysisJob else None,
            "analysisSummary": self.analysisSummary.to_dict() if self.analysisSummary else None,
            "parts": [item.to_dict() for item in self.parts],
            "timeline": [item.to_dict() for item in self.timeline],
            "soundMatches": [item.to_dict() for item in self.soundMatches],
            "guideSteps": [item.to_dict() for item in self.guideSteps],
            "mixPlan": self.mixPlan,
            "warnings": self.warnings,
        }
