"""Tests for :mod:`luonvuitoi_cert.engine.fonts`."""

from __future__ import annotations

from pathlib import Path

import pytest

from luonvuitoi_cert.engine.fonts import FontRegistry, FontRegistryError


def test_resolve_returns_absolute_path(cert_config, project_root: Path) -> None:  # type: ignore[no-untyped-def]
    reg = FontRegistry(cert_config, project_root)
    resolved = reg.resolve("serif")
    assert resolved.is_absolute()
    assert resolved.exists()


def test_resolve_unknown_key(cert_config, project_root: Path) -> None:  # type: ignore[no-untyped-def]
    reg = FontRegistry(cert_config, project_root)
    with pytest.raises(FontRegistryError, match="not declared"):
        reg.resolve("sans")


def test_resolve_missing_file(cert_config, project_root: Path) -> None:  # type: ignore[no-untyped-def]
    (project_root / "assets" / "fonts" / "serif.ttf").unlink()
    reg = FontRegistry(cert_config, project_root)
    with pytest.raises(FontRegistryError, match="missing"):
        reg.resolve("serif")


def test_ensure_loaded_is_idempotent(cert_config, project_root: Path) -> None:  # type: ignore[no-untyped-def]
    reg = FontRegistry(cert_config, project_root)
    reg.ensure_loaded("serif")
    # Second call must not re-register (would raise in reportlab otherwise).
    reg.ensure_loaded("serif")


def test_ensure_all_loaded(cert_config, project_root: Path) -> None:  # type: ignore[no-untyped-def]
    reg = FontRegistry(cert_config, project_root)
    reg.ensure_all_loaded()
    assert "serif" in FontRegistry._registered_globally


def test_ensure_loaded_reports_invalid_ttf(tmp_path: Path, cert_config) -> None:  # type: ignore[no-untyped-def]
    bogus = tmp_path / "assets" / "fonts" / "serif.ttf"
    bogus.parent.mkdir(parents=True, exist_ok=True)
    bogus.write_bytes(b"not a real ttf file")
    reg = FontRegistry(cert_config, tmp_path)
    with pytest.raises(FontRegistryError, match="ReportLab rejected"):
        reg.ensure_loaded("serif")
