from io import BytesIO
from zipfile import ZipFile

from app.contracts import Note, NotePayload
from app.reconstruction_contracts import PatternSlice, ReconstructionProject, ReconstructedPart, StemAsset
from app.reconstruction_export import build_reconstruction_export, midi_bytes


def project_with_pattern() -> ReconstructionProject:
    stem = StemAsset.create(
        fileName="bass.wav",
        storedName="bass.wav",
        relativePath="input/bass.wav",
        mediaType="audio/wav",
        sizeBytes=48,
        sha256="a" * 64,
        role="bass",
    )
    payload = NotePayload.create(
        title="Bass A",
        sourcePrompt="Owned reconstruction",
        genre="South African dance",
        bpm=114,
        key="G",
        scale="minor",
        bars=4,
        notes=[Note(pitch=43, startBeats=0, durationBeats=1, velocity=0.8)],
    )
    pattern = PatternSlice.create(name="Bass A", startBar=1, payload=payload)
    part = ReconstructedPart.create(
        sourceStemId=stem.id,
        name="Bass",
        role="bass",
        outputMode="midi",
        confidence=0.9,
        patterns=[pattern],
    )
    return ReconstructionProject.create(title="Owned", rightsAccepted=True).with_changes(
        status="review",
        stems=[stem],
        storageBytes=48,
        parts=[part],
        mixPlan={"title": "Mix", "steps": []},
    )


def test_midi_export_has_standard_header():
    payload = project_with_pattern().parts[0].patterns[0].payload

    data = midi_bytes(payload)

    assert data.startswith(b"MThd")
    assert b"MTrk" in data


def test_export_zip_contains_project_midi_and_reports(tmp_path):
    project = project_with_pattern()
    project_dir = tmp_path / project.id
    (project_dir / "input").mkdir(parents=True)
    (project_dir / "input" / "bass.wav").write_bytes(b"audio")

    archive = build_reconstruction_export(project, project_dir)
    with ZipFile(BytesIO(archive)) as bundle:
        names = set(bundle.namelist())

    assert "project.json" in names
    assert "analysis.json" in names
    assert "arrangement.json" in names
    assert "mix-plan.json" in names
    assert "recommendations.json" in names
    assert "guide-manifest.json" in names
    assert "midi/Bass/Bass A.mid" in names


def test_export_zip_contains_full_arrangement_spine(tmp_path):
    from app.reconstruction_export import build_reconstruction_export

    project = project_with_pattern()  # existing helper in this file; has a MIDI "Bass" part
    bundle_bytes = build_reconstruction_export(project, tmp_path)
    from io import BytesIO
    from zipfile import ZipFile

    with ZipFile(BytesIO(bundle_bytes)) as bundle:
        names = set(bundle.namelist())
    assert "arrangement.mid" in names
    assert "midi/Bass/Bass A.mid" in names  # per-pattern files still present

