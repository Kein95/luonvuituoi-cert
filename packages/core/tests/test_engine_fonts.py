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
    keys = {k for k, _ in FontRegistry._psname_by_path}
    assert "serif" in keys


def test_ensure_loaded_returns_psname(cert_config, project_root: Path) -> None:  # type: ignore[no-untyped-def]
    reg = FontRegistry(cert_config, project_root)
    psname = reg.ensure_loaded("serif")
    assert psname.startswith("serif_") and len(psname) > len("serif_")


def test_same_key_different_paths_do_not_collide(tmp_path: Path, config_dict: dict) -> None:  # type: ignore[no-untyped-def]
    """Regression: Phase 03 review C1 — previously project B's font silently replaced project A's."""
    import reportlab as rl

    rl_fonts = Path(rl.__file__).parent / "fonts"
    import shutil as _sh

    from luonvuitoi_cert.config import CertConfig

    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    for root, ttf_name in [(root_a, "Vera.ttf"), (root_b, "VeraBd.ttf")]:
        (root / "assets" / "fonts").mkdir(parents=True)
        _sh.copy2(rl_fonts / ttf_name, root / "assets" / "fonts" / "serif.ttf")
    cfg_a = CertConfig.model_validate({**config_dict, "fonts": {"serif": "assets/fonts/serif.ttf"}})
    cfg_b = CertConfig.model_validate({**config_dict, "fonts": {"serif": "assets/fonts/serif.ttf"}})
    ps_a = FontRegistry(cfg_a, root_a).ensure_loaded("serif")
    ps_b = FontRegistry(cfg_b, root_b).ensure_loaded("serif")
    assert ps_a != ps_b, "same font key from different roots must register under distinct PSNames"


def test_ensure_loaded_reports_invalid_ttf(tmp_path: Path, cert_config) -> None:  # type: ignore[no-untyped-def]
    bogus = tmp_path / "assets" / "fonts" / "serif.ttf"
    bogus.parent.mkdir(parents=True, exist_ok=True)
    bogus.write_bytes(b"not a real ttf file")
    reg = FontRegistry(cert_config, tmp_path)
    with pytest.raises(FontRegistryError, match="ReportLab rejected"):
        reg.ensure_loaded("serif")
