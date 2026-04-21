"""Tests for :mod:`luonvuitoi_cert.engine.renderer`."""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader

from luonvuitoi_cert.engine import OverlayError, OverlayRequest, render_certificate_bytes


def _make_request(config, project_root: Path, page: int = 1, **values: str) -> OverlayRequest:  # type: ignore[no-untyped-def]
    return OverlayRequest(
        config=config,
        project_root=project_root,
        round_id="main",
        page_number=page,
        values=values,
    )


def test_render_produces_single_page_pdf(cert_config, project_root: Path) -> None:  # type: ignore[no-untyped-def]
    req = _make_request(cert_config, project_root, name="Alice Example")
    out = render_certificate_bytes(req)
    assert isinstance(out, bytes) and len(out) > 500
    reader = PdfReader(__import__("io").BytesIO(out))
    assert len(reader.pages) == 1


def test_render_picks_correct_page(cert_config, project_root: Path) -> None:  # type: ignore[no-untyped-def]
    """Overlay must embed the selected template page, not page 1 always."""
    p1 = render_certificate_bytes(_make_request(cert_config, project_root, page=1))
    p2 = render_certificate_bytes(_make_request(cert_config, project_root, page=2))
    assert p1 != p2


def test_invalid_round_raises(cert_config, project_root: Path) -> None:  # type: ignore[no-untyped-def]
    req = OverlayRequest(cert_config, project_root, round_id="bogus", page_number=1, values={})
    with pytest.raises(OverlayError, match="round_id"):
        render_certificate_bytes(req)


def test_page_number_out_of_range(cert_config, project_root: Path) -> None:  # type: ignore[no-untyped-def]
    req = _make_request(cert_config, project_root, page=99)
    with pytest.raises(OverlayError, match="out of range"):
        render_certificate_bytes(req)


def test_page_number_zero_rejected(cert_config, project_root: Path) -> None:  # type: ignore[no-untyped-def]
    req = _make_request(cert_config, project_root, page=0)
    with pytest.raises(OverlayError, match="out of range"):
        render_certificate_bytes(req)


def test_unknown_field_silently_ignored(cert_config, project_root: Path) -> None:  # type: ignore[no-untyped-def]
    req = _make_request(cert_config, project_root, name="Alice", not_declared_in_layout="junk")
    out = render_certificate_bytes(req)
    assert len(out) > 500  # renders, no exception


def test_empty_value_does_not_break(cert_config, project_root: Path) -> None:  # type: ignore[no-untyped-def]
    req = _make_request(cert_config, project_root, name="")
    out = render_certificate_bytes(req)
    assert len(out) > 500


def test_whitespace_only_value_is_skipped(cert_config, project_root: Path) -> None:
    """Phase 03 review H2: ``' '`` used to draw a blank over the template."""
    req = _make_request(cert_config, project_root, name="   ")
    out = render_certificate_bytes(req)
    assert len(out) > 500  # renders, but name field is skipped


def test_value_exceeding_max_length_raises(cert_config, project_root: Path) -> None:
    """Phase 03 review H2: cap adversarial input sizes at the engine boundary."""
    from luonvuitoi_cert.engine.renderer import MAX_FIELD_LENGTH

    req = _make_request(cert_config, project_root, name="x" * (MAX_FIELD_LENGTH + 1))
    with pytest.raises(OverlayError, match="MAX_FIELD_LENGTH"):
        render_certificate_bytes(req)


def test_non_string_value_is_coerced(cert_config, project_root: Path) -> None:
    """Numbers, etc., still render (coerced via ``str()``)."""
    req = _make_request(cert_config, project_root, name=12345)  # type: ignore[arg-type]
    out = render_certificate_bytes(req)
    assert len(out) > 500


def test_missing_template_file(cert_config, project_root: Path) -> None:  # type: ignore[no-untyped-def]
    (project_root / "templates" / "main.pdf").unlink()
    req = _make_request(cert_config, project_root, name="X")
    with pytest.raises(OverlayError, match="template PDF missing"):
        render_certificate_bytes(req)


def test_wrap_splits_long_school_name(cert_config, project_root: Path, config_dict: dict) -> None:  # type: ignore[no-untyped-def]
    """School with wrap=30 should fit across multiple lines without raising."""
    from luonvuitoi_cert.config import CertConfig

    config_dict["layout"]["fields"]["school"] = {
        "x": 421,
        "y": 300,
        "font": "serif",
        "size": 14,
        "align": "center",
        "wrap": 30,
    }
    cfg = CertConfig.model_validate(config_dict)
    long_name = "A really very exceedingly long school name that needs wrapping indeed"
    req = OverlayRequest(cfg, project_root, "main", 1, {"school": long_name, "name": "A."})
    out = render_certificate_bytes(req)
    assert len(out) > 500
