from app.analysis import AnalysisResult
from app.inventory import InventorySnapshot
from app.reconstruction_compiler import ReconstructionCompiler
from app.reconstruction_contracts import ReconstructionProject, StemAsset


def stem(name: str, role: str) -> StemAsset:
    return StemAsset.create(
        fileName=name,
        storedName=name,
        relativePath=f"input/{name}",
        mediaType="audio/wav",
        sizeBytes=48,
        sha256=(name[0].lower() * 64),
        role=role,
    )


def test_compiler_splits_long_midi_parts_and_keeps_vocals_as_audio():
    bass = stem("bass.wav", "bass")
    vocals = stem("vocals.wav", "vocals")
    project = ReconstructionProject.create(title="Owned", rightsAccepted=True).with_changes(
        status="uploaded",
        stems=[bass, vocals],
        storageBytes=96,
    )
    result = AnalysisResult.from_dict(
        {
            "summary": {
                "bpm": 114,
                "bpmConfidence": 0.96,
                "key": "G",
                "scale": "minor",
                "keyConfidence": 0.85,
                "timeSignature": "4/4",
                "durationSeconds": 84.21,
                "sections": [],
            },
            "stems": [
                {
                    "stemId": bass.id,
                    "role": "bass",
                    "confidence": 0.87,
                    "notes": [
                        {"pitch": 43, "startBeats": 0, "durationBeats": 1, "velocity": 0.8},
                        {"pitch": 50, "startBeats": 130, "durationBeats": 1, "velocity": 0.7},
                    ],
                    "warnings": [],
                },
                {
                    "stemId": vocals.id,
                    "role": "vocals",
                    "confidence": 0.95,
                    "notes": [],
                    "warnings": [],
                },
            ],
        }
    )

    compiled = ReconstructionCompiler().compile(
        project,
        result,
        inventory=InventorySnapshot.empty(),
    )

    bass_part = next(part for part in compiled.parts if part.role == "bass")
    vocal_part = next(part for part in compiled.parts if part.role == "vocals")
    assert [pattern.bars for pattern in bass_part.patterns] == [32, 8]
    assert bass_part.patterns[1].payload.notes[0].startBeats == 2
    assert vocal_part.outputMode == "audio"
    assert vocal_part.audioRelativePath == "input/vocals.wav"
    assert compiled.status == "review"
    assert compiled.mixPlan["steps"]
    assert compiled.guideSteps[0].imageAsset.startswith("/guides/fl-2025/")


def test_compiler_defaults_low_confidence_material_to_audio():
    other = stem("other.wav", "other")
    project = ReconstructionProject.create(title="Owned", rightsAccepted=True).with_changes(
        status="uploaded", stems=[other], storageBytes=48
    )
    result = AnalysisResult.from_dict(
        {
            "summary": {
                "bpm": 114,
                "bpmConfidence": 0.8,
                "key": "G",
                "scale": "minor",
                "keyConfidence": 0.7,
                "timeSignature": "4/4",
                "durationSeconds": 16.84,
                "sections": [],
            },
            "stems": [
                {
                    "stemId": other.id,
                    "role": "melody",
                    "confidence": 0.58,
                    "notes": [{"pitch": 67, "startBeats": 0, "durationBeats": 1}],
                    "warnings": ["Dense texture"],
                }
            ],
        }
    )

    compiled = ReconstructionCompiler().compile(project, result, InventorySnapshot.empty())

    assert compiled.parts[0].outputMode == "audio"
    assert compiled.parts[0].requiresReview is False


def test_guide_steps_describe_the_send_to_fl_loop():
    from app.reconstruction_compiler import ReconstructionCompiler

    steps = ReconstructionCompiler()._guide_steps()
    titles = [step.title for step in steps]

    assert any("arrangement MIDI" in title for title in titles)
    assert any("Sync FL" in title for title in titles)
    assert all(step.imageAsset.startswith("/guides/fl-2025/") for step in steps)

