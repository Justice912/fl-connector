import json
from pathlib import Path

import pytest

from app.inventory import InventoryScanner, recommend_sounds
from app.reconstruction_contracts import ReconstructionError


def test_inventory_scans_plugins_and_prefers_installed_bass_sound(tmp_path: Path):
    plugins = tmp_path / "Plugin database" / "Generators"
    plugins.mkdir(parents=True)
    (plugins / "BooBass.fst").write_bytes(b"preset")
    (plugins / "FLEX.fst").write_bytes(b"preset")

    snapshot = InventoryScanner([tmp_path]).scan()
    matches = recommend_sounds("bass", snapshot, catalog=[])

    assert {item.name for item in snapshot.items} == {"BooBass", "FLEX"}
    assert matches[0].name == "BooBass"
    assert matches[0].installed is True


def test_inventory_rejects_download_catalog_entry_without_license(tmp_path: Path):
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            [
                {
                    "name": "Mystery Pack",
                    "roles": ["log_drum"],
                    "url": "https://example.test/pack",
                    "priceClass": "free",
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReconstructionError, match="license"):
        InventoryScanner.load_catalog(catalog_path)

