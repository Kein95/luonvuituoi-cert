"""Tests for :mod:`luonvuitoi_cert.config.loader` and bundled samples.

The loader is the single entry point CLI tools and serverless handlers call,
so its error messages must survive refactors. Sample configs double as
regression fixtures — if they stop validating, downstream docs and scaffolder
templates break.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from luonvuitoi_cert.config import CertConfig, load_config, load_config_dict
from luonvuitoi_cert.config.loader import ConfigError

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "luonvuitoi_cert" / "config" / "samples"


@pytest.mark.parametrize("name", ["minimal.json", "full.json", "qr-only.json"])
def test_shipped_samples_validate(name: str) -> None:
    cfg = load_config(SAMPLES_DIR / name)
    assert isinstance(cfg, CertConfig)
    assert cfg.project.slug.startswith("demo-academy")


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.json")


def test_load_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not a file"):
        load_config(tmp_path)


def test_load_invalid_json_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid JSON"):
        load_config(p)


def test_load_non_object_root_raises(tmp_path: Path) -> None:
    p = tmp_path / "list.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ConfigError, match="root must be a JSON object"):
        load_config(p)


def test_load_validation_error_wraps_cleanly(tmp_path: Path) -> None:
    p = tmp_path / "malformed.json"
    p.write_text(json.dumps({"project": {"name": "x", "slug": "x"}}), encoding="utf-8")
    with pytest.raises(ConfigError, match="failed validation"):
        load_config(p)


def test_load_config_dict_short_circuits() -> None:
    raw = json.loads((SAMPLES_DIR / "minimal.json").read_text(encoding="utf-8"))
    raw.pop("$schema", None)
    cfg = load_config_dict(raw)
    assert cfg.subjects[0].code == "S"


def test_samples_reference_cert_schema() -> None:
    """Keep editor autocomplete wired up in every shipped sample."""
    for name in ("minimal.json", "full.json", "qr-only.json"):
        raw = json.loads((SAMPLES_DIR / name).read_text(encoding="utf-8"))
        assert raw.get("$schema", "").endswith("cert.schema.json"), name
