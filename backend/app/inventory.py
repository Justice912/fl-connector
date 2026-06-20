from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .reconstruction_contracts import ReconstructionError, SoundMatch

PLUGIN_SUFFIXES = {".fst", ".vst3", ".dll"}
SAMPLE_SUFFIXES = {".wav", ".flac", ".mp3", ".aif", ".aiff"}
ROLE_PREFERENCES = {
    "drums": ["FPC", "Sampler"],
    "percussion": ["FPC", "FLEX"],
    "bass": ["BooBass", "3xOsc", "FLEX"],
    "chords": ["FLEX", "Sytrus"],
    "log_drum": ["FLEX", "FPC"],
    "melody": ["FLEX", "Sytrus"],
    "guitar": ["FLEX"],
    "vocals": ["Audio Clip"],
    "fx": ["Sampler"],
    "other": ["FLEX", "Sampler"],
}


@dataclass(frozen=True)
class InventoryItem:
    id: str
    name: str
    kind: str
    path: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name, "kind": self.kind, "path": self.path}


@dataclass(frozen=True)
class InventorySnapshot:
    items: list[InventoryItem]
    roots: list[str]

    @classmethod
    def empty(cls) -> "InventorySnapshot":
        return cls(items=[], roots=[])

    def to_dict(self) -> dict[str, object]:
        return {"items": [item.to_dict() for item in self.items], "roots": self.roots}


class InventoryScanner:
    def __init__(self, roots: list[Path], max_items: int = 20000) -> None:
        self.roots = [Path(root) for root in roots]
        self.max_items = max_items

    def scan(self) -> InventorySnapshot:
        found: dict[tuple[str, str], InventoryItem] = {}
        for root in self.roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                suffix = path.suffix.lower()
                if suffix in PLUGIN_SUFFIXES and (path.is_file() or suffix == ".vst3"):
                    kind = "plugin"
                elif suffix in SAMPLE_SUFFIXES and path.is_file():
                    kind = "sample"
                else:
                    continue
                name = _display_name(path)
                key = (kind, name.casefold())
                found.setdefault(
                    key,
                    InventoryItem(
                        id=f"{kind}:{_slug(name)}",
                        name=name,
                        kind=kind,
                        path=str(path),
                    ),
                )
                if len(found) >= self.max_items:
                    break
            if len(found) >= self.max_items:
                break
        return InventorySnapshot(
            items=sorted(found.values(), key=lambda item: (item.kind, item.name.casefold())),
            roots=[str(root) for root in self.roots if root.exists()],
        )

    @staticmethod
    def load_catalog(path: Path) -> list[dict[str, Any]]:
        if not Path(path).exists():
            return []
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(value, list):
            raise ReconstructionError("recommendation catalog must be a list")
        catalog: list[dict[str, Any]] = []
        for entry in value:
            if not isinstance(entry, dict):
                raise ReconstructionError("recommendation catalog entries must be objects")
            if not entry.get("url") or not entry.get("licenseUrl") or not entry.get("licenseName"):
                raise ReconstructionError("download recommendations require license metadata")
            if not entry.get("roles"):
                raise ReconstructionError("download recommendations require at least one role")
            catalog.append(dict(entry))
        return catalog


def recommend_sounds(
    role: str,
    inventory: InventorySnapshot,
    catalog: list[dict[str, Any]],
) -> list[SoundMatch]:
    preferences = ROLE_PREFERENCES.get(role, ROLE_PREFERENCES["other"])
    installed: list[SoundMatch] = []
    for rank, preferred in enumerate(preferences):
        for item in inventory.items:
            if preferred.casefold() not in item.name.casefold():
                continue
            installed.append(
                SoundMatch.from_dict(
                    {
                        "id": item.id,
                        "name": item.name,
                        "kind": item.kind,
                        "installed": True,
                        "source": "inventory",
                        "score": max(0.5, 1 - rank * 0.12),
                        "reason": f"Installed match for {role.replace('_', ' ')}.",
                        "path": item.path,
                        "priceClass": "installed",
                    }
                )
            )
    external: list[SoundMatch] = []
    for entry in catalog:
        if role not in entry.get("roles", []):
            continue
        external.append(
            SoundMatch.from_dict(
                {
                    "id": str(entry.get("id", f"catalog:{_slug(str(entry['name']))}")),
                    "name": str(entry["name"]),
                    "kind": str(entry.get("kind", "plugin")),
                    "installed": False,
                    "source": "catalog",
                    "score": float(entry.get("score", 0.62)),
                    "reason": str(entry.get("reason", f"Curated {role} alternative.")),
                    "url": str(entry["url"]),
                    "licenseName": str(entry["licenseName"]),
                    "licenseUrl": str(entry["licenseUrl"]),
                    "priceClass": str(entry.get("priceClass", "paid")),
                    "platform": str(entry.get("platform", "Windows")),
                }
            )
        )
    unique: dict[tuple[str, str], SoundMatch] = {}
    for match in [*installed, *external]:
        unique.setdefault((match.source, match.name.casefold()), match)
    return sorted(unique.values(), key=lambda item: (not item.installed, -item.score, item.name))


def _display_name(path: Path) -> str:
    return re.sub(r"[_-]+", " ", path.stem).strip()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")

