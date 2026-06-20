import pytest

from app.contracts import Note, NotePayload
from app.reconstruction_contracts import (
    AnalysisJob,
    PatternSlice,
    ReconstructionError,
    ReconstructionProject,
    ReconstructedPart,
    StemAsset,
)


def payload(*, bars: int = 4) -> NotePayload:
    return NotePayload.create(
        title="Bass pattern",
        sourcePrompt="Reconstructed from an owned stem",
        genre="South African dance",
        bpm=114,
        key="G",
        scale="minor",
        bars=bars,
        notes=[Note(pitch=43, startBeats=0, durationBeats=1)],
    )


def test_project_requires_rights_confirmation():
    with pytest.raises(ReconstructionError, match="ownership or permission"):
        ReconstructionProject.create(title="Owned song", rightsAccepted=False)


def test_pattern_slice_rejects_more_than_32_bars():
    with pytest.raises(ReconstructionError, match="32 bars"):
        PatternSlice.create(
            name="Oversized section",
            startBar=1,
            payload=payload(bars=32),
            bars=33,
        )


def test_project_round_trips_stems_job_and_midi_part():
    project = ReconstructionProject.create(title="Midnight Township", rightsAccepted=True)
    stem = StemAsset.create(
        fileName="bass.wav",
        storedName="bass.wav",
        relativePath="input/bass.wav",
        mediaType="audio/wav",
        sizeBytes=48,
        sha256="a" * 64,
        role="bass",
    )
    pattern = PatternSlice.create(name="Bass A", startBar=1, payload=payload(), bars=4)
    part = ReconstructedPart.create(
        sourceStemId=stem.id,
        name="Bass",
        role="bass",
        outputMode="midi",
        confidence=0.87,
        patterns=[pattern],
    )
    hydrated = ReconstructionProject.from_dict(
        {
            **project.to_dict(),
            "status": "review",
            "stems": [stem.to_dict()],
            "analysisJob": AnalysisJob.create().to_dict(),
            "parts": [part.to_dict()],
        }
    )

    assert hydrated.title == "Midnight Township"
    assert hydrated.stems[0].role == "bass"
    assert hydrated.parts[0].patterns[0].payload.bpm == 114
    assert hydrated.parts[0].requiresReview is False

