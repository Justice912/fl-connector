from __future__ import annotations

from math import ceil

from .analysis import AnalysisResult, StemAnalysis
from .contracts import Note, NotePayload
from .inventory import InventorySnapshot, recommend_sounds
from .reconstruction_contracts import (
    AnalysisSummary,
    GuideStep,
    PatternSlice,
    ReconstructionProject,
    ReconstructedPart,
    TimelineSection,
)

INSTRUMENT_HINTS = {
    "drums": "FPC with kick, clap, hat, shaker, and percussion pads",
    "percussion": "FPC or FLEX percussion preset",
    "bass": "BooBass or 3xOsc with centered low end",
    "chords": "FLEX warm keys or pad preset",
    "log_drum": "FLEX mallet preset or an owned tuned log drum sample",
    "melody": "FLEX pluck, bell, or keys preset",
    "guitar": "FLEX guitar preset or aligned audio",
    "vocals": "Playlist Audio Clip",
    "fx": "Playlist Audio Clip or Sampler",
    "other": "FLEX, Sampler, or aligned audio",
}


class ReconstructionCompiler:
    def __init__(self, catalog: list[dict[str, object]] | None = None) -> None:
        self.catalog = list(catalog or [])

    def compile(
        self,
        project: ReconstructionProject,
        result: AnalysisResult,
        inventory: InventorySnapshot,
    ) -> ReconstructionProject:
        stems = {stem.id: stem for stem in project.stems}
        total_bars = max(1, ceil(result.summary.durationSeconds * result.summary.bpm / 240))
        timeline = self._timeline(total_bars, result.summary.bpm)
        parts: list[ReconstructedPart] = []
        matches = []
        for item in result.stems:
            stem = stems.get(item.stemId)
            if stem is None:
                continue
            mode = self._output_mode(item)
            patterns = self._patterns(project, stem.fileName, item, result, total_bars) if mode == "midi" else []
            if mode == "midi" and not patterns:
                mode = "audio"
            part = ReconstructedPart.create(
                sourceStemId=stem.id,
                name=stem.fileName.rsplit(".", 1)[0],
                role=item.role,
                outputMode=mode,
                confidence=item.confidence,
                patterns=patterns,
                audioRelativePath=stem.relativePath if mode == "audio" else None,
                instrumentHint=INSTRUMENT_HINTS.get(item.role, INSTRUMENT_HINTS["other"]),
            )
            part = ReconstructedPart.from_dict({**part.to_dict(), "warnings": item.warnings})
            parts.append(part)
            matches.extend(recommend_sounds(item.role, inventory, self.catalog))

        timeline = [
            TimelineSection.from_dict(
                {
                    **section.to_dict(),
                    "activePartIds": [part.id for part in parts],
                }
            )
            for section in timeline
        ]
        summary = AnalysisSummary.from_dict(
            {**result.summary.to_dict(), "sections": [section.to_dict() for section in timeline]}
        )
        unique_matches = {}
        for match in matches:
            unique_matches.setdefault((match.source, match.name.casefold()), match)
        return project.with_changes(
            status="review",
            analysisSummary=summary,
            parts=parts,
            timeline=timeline,
            soundMatches=list(unique_matches.values()),
            mixPlan=self._mix_plan(parts),
            guideSteps=self._guide_steps(),
            warnings=[
                "This is a faithful reconstruction from audio evidence, not the original Suno project."
            ],
        )

    @staticmethod
    def _output_mode(item: StemAnalysis) -> str:
        if item.role in {"vocals", "fx"} or item.confidence < 0.60 or not item.notes:
            return "audio"
        return "midi"

    @staticmethod
    def _patterns(
        project: ReconstructionProject,
        stem_name: str,
        item: StemAnalysis,
        result: AnalysisResult,
        total_bars: int,
    ) -> list[PatternSlice]:
        patterns: list[PatternSlice] = []
        total_beats = total_bars * 4
        for start_beat in range(0, total_beats, 128):
            chunk_bars = min(32, ceil((total_beats - start_beat) / 4))
            chunk_end = start_beat + chunk_bars * 4
            notes = []
            for source in item.notes:
                if not start_beat <= source.startBeats < chunk_end:
                    continue
                local_start = source.startBeats - start_beat
                duration = min(source.durationBeats, chunk_bars * 4 - local_start)
                notes.append(
                    Note(
                        pitch=source.pitch,
                        startBeats=local_start,
                        durationBeats=max(0.01, duration),
                        velocity=source.velocity,
                        color=source.color,
                        pan=source.pan,
                        slide=source.slide,
                        porta=source.porta,
                        muted=source.muted,
                    )
                )
            if not notes:
                continue
            start_bar = start_beat // 4 + 1
            payload = NotePayload.create(
                title=f"{stem_name.rsplit('.', 1)[0]} bars {start_bar}-{start_bar + chunk_bars - 1}",
                sourcePrompt=f"Reconstructed from owned stem {stem_name}",
                genre="South African dance",
                bpm=round(result.summary.bpm),
                key=result.summary.key,
                scale=result.summary.scale,
                bars=chunk_bars,
                notes=notes,
            )
            patterns.append(
                PatternSlice.create(
                    name=payload.title,
                    startBar=start_bar,
                    bars=chunk_bars,
                    payload=payload,
                )
            )
        return patterns

    @staticmethod
    def _timeline(total_bars: int, bpm: float) -> list[TimelineSection]:
        if total_bars < 8:
            lengths = [total_bars]
            names = ["Full song"]
        else:
            first = max(2, total_bars // 5)
            second = max(2, total_bars // 3)
            third = max(2, total_bars // 3)
            fourth = total_bars - first - second - third
            if fourth < 1:
                third += fourth - 1
                fourth = 1
            lengths = [first, second, third, fourth]
            names = ["Intro", "Groove", "Drop", "Outro"]
        sections = []
        start_bar = 1
        seconds_per_bar = 240 / bpm
        for name, bars in zip(names, lengths, strict=True):
            start_seconds = (start_bar - 1) * seconds_per_bar
            end_seconds = (start_bar - 1 + bars) * seconds_per_bar
            sections.append(
                TimelineSection.from_dict(
                    {
                        "name": name,
                        "startSeconds": start_seconds,
                        "endSeconds": end_seconds,
                        "startBar": start_bar,
                        "bars": bars,
                        "activePartIds": [],
                    }
                )
            )
            start_bar += bars
        return sections

    @staticmethod
    def _mix_plan(parts: list[ReconstructedPart]) -> dict[str, object]:
        steps = []
        order = 1
        for part in parts:
            steps.append(
                {
                    "order": order,
                    "targetPartId": part.id,
                    "targetLabel": part.name,
                    "plugin": "Fruity Parametric EQ 2",
                    "slot": 1,
                    "action": "Remove frequencies that do not serve this layer.",
                    "settings": {"Start": "Use small moves and level-match before/after."},
                    "clickPath": f"Press F9 > select {part.name} mixer track > slot 1 > Fruity Parametric EQ 2",
                }
            )
            order += 1
        steps.extend(
            [
                {
                    "order": order,
                    "targetPartId": None,
                    "targetLabel": "Master",
                    "plugin": "Maximus",
                    "slot": 2,
                    "action": "Apply gentle multiband glue.",
                    "settings": {"Preset": "Clear Master or Default; adjust gently."},
                    "clickPath": "Press F9 > Master > slot 2 > Maximus",
                },
                {
                    "order": order + 1,
                    "targetPartId": None,
                    "targetLabel": "Master",
                    "plugin": "Fruity Limiter",
                    "slot": 3,
                    "action": "Protect the final output from clipping.",
                    "settings": {"Ceiling": "-1 dB"},
                    "clickPath": "Press F9 > Master > slot 3 > Fruity Limiter",
                },
            ]
        )
        return {
            "title": "Analysis-derived built-in FL mix plan",
            "status": "draft",
            "steps": steps,
            "safetyNotes": [
                "Balance channel levels before mastering.",
                "Keep kick and bass centered; widen pads and percussion instead.",
            ],
        }

    @staticmethod
    def _guide_steps() -> list[GuideStep]:
        rows = [
            (
                "Open the Channel Rack",
                "Channel Rack",
                "Open the instrument and pattern list.",
                "View > Channel rack",
                "F6",
                "/guides/fl-2025/channel-rack.png",
                "The Channel Rack is visible.",
            ),
            (
                "Add the approved instrument",
                "Channel Rack",
                "Use the plus button and choose the approved installed sound.",
                "Channel Rack > + button > approved instrument",
                None,
                "/guides/fl-2025/add-instrument.png",
                "The new channel appears in the Channel Rack.",
            ),
            (
                "Apply the MIDI pattern",
                "Piano Roll",
                "Open the selected channel Piano Roll and apply the approved pattern.",
                "Tools > Scripts > FL Connector Apply Payload",
                "F7",
                "/guides/fl-2025/apply-payload.png",
                "The reconstructed notes appear in the Piano Roll.",
            ),
            (
                "Arrange the song",
                "Playlist",
                "Place patterns and audio clips at their listed start bars.",
                "View > Playlist",
                "F5",
                "/guides/fl-2025/playlist.png",
                "Patterns and clips line up with the blueprint sections.",
            ),
            (
                "Apply the mix plan",
                "Mixer",
                "Route each channel and add the approved built-in effects.",
                "View > Mixer",
                "F9",
                "/guides/fl-2025/mixer.png",
                "Each blueprint channel has its own Mixer track.",
            ),
        ]
        return [
            GuideStep.from_dict(
                {
                    "order": index,
                    "title": title,
                    "area": area,
                    "action": action,
                    "menuPath": menu,
                    "shortcut": shortcut,
                    "imageAsset": image,
                    "hotspot": {"x": 0.08, "y": 0.08, "width": 0.18, "height": 0.12},
                    "expectedState": expected,
                }
            )
            for index, (title, area, action, menu, shortcut, image, expected) in enumerate(rows, 1)
        ]

