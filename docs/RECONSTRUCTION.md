# Suno Stem-to-FL Reconstruction

## Scope

The Rebuild workspace turns user-owned or permissioned stems into a faithful,
editable FL Studio 2025 reconstruction. It estimates musical evidence and
builds a practical Channel Rack order, Piano Roll patterns, Playlist placement,
Mixer routing plan, sound recommendations, and step-by-step guide.

It cannot recover Suno's hidden presets, generation seed, original MIDI,
automation, mixer settings, or mastering chain. Full-mix source separation,
automatic `.flp` generation, cloud analysis, unverified plugin insertion, and
automatic sound downloads are not part of this version.

## Local Analysis Setup

Normal reconstruction runs locally. Before the first analysis:

1. Install official 64-bit Python 3.11 and verify `py -3.11 --version`.
2. Install FFmpeg from a trusted official distribution and verify
   `ffmpeg -version`.
3. In `Rebuild`, review the setup checks and confirm `Approve local install`.
4. Click `Install worker` only when the button is enabled.
5. The connector creates `.analysis-worker`, installs the pinned packages from
   `backend/analysis-worker-requirements.txt`, and reruns compatibility checks.

Analysis stays blocked unless Python 3.11, FFmpeg, Basic Pitch, librosa,
SoundFile, NumPy, SciPy, and pyloudnorm all pass. No fallback transcription
engine is selected silently.

## Upload Rules

- Accepted input: ZIP, WAV, MP3, FLAC, and M4A.
- Maximum 20 audio files per project.
- Maximum 1 GB stored per project.
- Maximum 15 decoded minutes per file.
- ZIP paths, compression ratios, signatures, duplicate names, and extension
  spoofing are validated before files are accepted.
- Files stay under `.data/reconstructions/<project-id>` until deletion.

Every project requires ownership or permission confirmation before creation.

## Review Policy

Drums use onset and frequency-band classification. Bass uses monophonic pitch
tracking. Other pitched material uses polyphonic transcription. Vocals and
textures stay as aligned audio by default.

- Confidence `>= 0.80`: editable MIDI candidate.
- Confidence `0.60-0.79`: editable MIDI with mandatory review badge.
- Confidence `< 0.60`: aligned audio by default.

Tempo or key corrections clear dependent analysis artifacts and require a new
analysis. Pattern corrections reset that pattern to draft. A MIDI pattern is
written to the existing FL payload only after approval.

A reconstruction reaches `approved` only after all parts are approved, every
MIDI part has a selected sound recommendation, and all FL guide steps are
complete. Older saved projects with partial acceptance are displayed as
`review` until those conditions are met.

The Rebuild workspace includes an acceptance gate panel that summarizes part
approval, sound choices, FL walkthrough completion, and detected-key confidence
before final handoff.

## FL Studio Workflow

1. Create the listed channels in Channel Rack order.
2. Choose an installed-first recommendation or select another owned sound.
3. For MIDI parts, open the matching Piano Roll with `F7`.
4. Approve the pattern in Rebuild.
5. Run `Tools > Scripts > FL Connector Apply Payload` in the Piano Roll.
6. Place patterns at their listed start bars in the Playlist with `F5`.
7. Add aligned audio clips at the listed start time and preserve their start.
8. Route each channel to its listed Mixer track with `F9`.
9. Apply the built-in mix plan with small, level-matched moves.

The live Flapi bridge may be offline during upload, analysis, review, export,
and manual Piano Roll application.

## API Surface

Setup:

- `GET /api/analysis/setup`
- `POST /api/analysis/setup/install`

Projects and files:

- `POST /api/reconstructions`
- `GET /api/reconstructions`
- `GET`, `PATCH`, `DELETE /api/reconstructions/{id}`
- `POST /api/reconstructions/{id}/stems`
- `GET /api/reconstructions/{id}/stems/{stemId}/content`
- `POST /api/reconstructions/{id}/analyze`
- `POST /api/reconstructions/{id}/retry`

Review and delivery:

- `PATCH /api/reconstructions/{id}/parts/{partId}`
- `PATCH /api/reconstructions/{id}/parts/{partId}/patterns/{patternId}`
- `POST /api/reconstructions/{id}/parts/{partId}/patterns/{patternId}/approve`
- `POST /api/reconstructions/{id}/parts/{partId}/approve-audio`
- `GET /api/reconstructions/{id}/guide`
- `PATCH /api/reconstructions/{id}/guide/{stepId}`
- `GET /api/inventory` and `POST /api/inventory/refresh`
- `GET /api/reconstructions/{id}/export`

## Export Bundle

The ZIP contains `project.json`, `analysis.json`, `arrangement.json`,
`mix-plan.json`, `recommendations.json`, `guide-manifest.json`, approved audio
stems, and one Standard MIDI file for every reconstructed pattern.

## Guide Asset Provenance

`frontend/public/guides/fl-2025` currently contains original instructional
maps, not FL Studio screenshots. This avoids presenting fabricated software UI
as a real capture. During user-owned practical acceptance, replace those assets
with blank-project FL Studio 2025 screenshots while preserving their file names,
responsive hotspot coordinates, and accessible descriptions.
