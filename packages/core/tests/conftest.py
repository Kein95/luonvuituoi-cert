"""Shared pytest fixtures for engine tests.

Uses the Bitstream Vera TTFs that ship with ReportLab (Apache 2.0) so tests
don't need any font assets of their own.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import reportlab
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

_REPORTLAB_FONTS = Path(reportlab.__file__).parent / "fonts"
VERA_TTF = _REPORTLAB_FONTS / "Vera.ttf"


@pytest.fixture
def fake_font_file(tmp_path: Path) -> Path:
    """Copy the bundled Vera.ttf into ``tmp_path/assets/fonts/serif.ttf``."""
    dest = tmp_path / "assets" / "fonts" / "serif.ttf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(VERA_TTF, dest)
    return dest


@pytest.fixture
def fake_template_pdf(tmp_path: Path) -> Path:
    """Write a 2-page placeholder template PDF with page labels."""
    dest = tmp_path / "templates" / "main.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for label in ("GOLD", "SILVER"):
        scratch = tmp_path / f"_page_{label}.pdf"
        c = canvas.Canvas(str(scratch), pagesize=A4)
        c.drawString(100, 750, f"TEMPLATE PAGE: {label}")
        c.showPage()
        c.save()
        writer.add_page(PdfReader(str(scratch)).pages[0])
    with dest.open("wb") as f:
        writer.write(f)
    return dest


@pytest.fixture
def project_root(tmp_path: Path, fake_font_file: Path, fake_template_pdf: Path) -> Path:
    """A valid project_root directory with fonts + template in expected locations."""
    return tmp_path


@pytest.fixture
def config_dict() -> dict:
    """Minimal valid config referencing the fixtures above (paths are relative)."""
    return {
        "project": {"name": "Test", "slug": "test"},
        "rounds": [{"id": "main", "label": "Main", "table": "students", "pdf": "templates/main.pdf"}],
        "subjects": [{"code": "S", "en": "Science", "db_col": "s"}],
        "results": {"S": {"GOLD": 1, "SILVER": 2}},
        "layout": {
            "page_size": [842, 595],
            "fields": {
                "name": {"x": 421, "y": 400, "font": "serif", "size": 24, "align": "center"}
            },
        },
        "fonts": {"serif": "assets/fonts/serif.ttf"},
    }


@pytest.fixture
def cert_config(config_dict: dict):  # type: ignore[no-untyped-def]
    from luonvuitoi_cert.config import CertConfig

    return CertConfig.model_validate(config_dict)


@pytest.fixture(autouse=True)
def _reset_font_registry():
    """Clear FontRegistry's process-wide cache between tests so registration is re-exercised."""
    from luonvuitoi_cert.engine.fonts import FontRegistry

    FontRegistry._psname_by_path.clear()
    yield
    FontRegistry._psname_by_path.clear()
