"""Smoke tests for the ``examples/demo-academy/`` reference project.

Guards against config drift — someone updates schema, forgets to update the
shipped example, and the demo quietly breaks for every new user. Also asserts
the Phase 12 zero-leak contract: no ASMO/SEAMO/IKLC strings in the committed
config.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from luonvuitoi_cert.config import load_config

EXAMPLE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "examples" / "demo-academy"


@pytest.mark.skipif(
    not (EXAMPLE_DIR / "cert.config.json").exists(),
    reason="examples/demo-academy not present — run from repo root.",
)
def test_demo_config_validates() -> None:
    cfg = load_config(EXAMPLE_DIR / "cert.config.json")
    assert cfg.project.slug == "demo-academy"
    assert cfg.features.qr_verify.enabled
    assert cfg.features.shipment.enabled


@pytest.mark.skipif(
    not (EXAMPLE_DIR / "cert.config.json").exists(),
    reason="examples/demo-academy not present.",
)
def test_demo_config_has_no_private_source_strings() -> None:
    raw = (EXAMPLE_DIR / "cert.config.json").read_text(encoding="utf-8").lower()
    for forbidden in ("asmo", "seamo", "iklc", "iksc", "hkimo"):
        assert forbidden not in raw


@pytest.mark.skipif(
    not (EXAMPLE_DIR / "cert.config.json").exists(),
    reason="examples/demo-academy not present.",
)
def test_demo_shipment_public_fields_are_subset() -> None:
    """Defense in depth: public_fields must remain a real subset of fields."""
    data = json.loads((EXAMPLE_DIR / "cert.config.json").read_text(encoding="utf-8"))
    ship = data["features"]["shipment"]
    assert set(ship.get("public_fields", [])).issubset(set(ship["fields"]))


@pytest.mark.skipif(
    not (EXAMPLE_DIR / "prepare_demo.py").exists(),
    reason="examples/demo-academy/prepare_demo.py not present.",
)
def test_prepare_demo_copies_expected_font_slots() -> None:
    """The script must provision the font keys declared in cert.config.json."""
    cfg = load_config(EXAMPLE_DIR / "cert.config.json")
    assert set(cfg.fonts.keys()) == {"script", "serif"}
    for font_key, relative_path in cfg.fonts.items():
        # Paths are relative; the .ttf file lands there only after prepare_demo runs.
        # We just assert the config side of the contract; the file presence isn't
        # part of a committed-repo invariant.
        assert relative_path.endswith(".ttf"), (font_key, relative_path)
