"""PDF overlay renderer: composite per-student text onto a template page.

A certificate template is a multi-page PDF where each page is one award
variant. This module accepts a template, a 1-indexed page number, and a
``values`` mapping keyed by the same field names declared in
``CertConfig.layout.fields``, and emits a single-page PDF with the text drawn
over the template.

Design notes:
- Page size comes from the template's actual MediaBox, not from
  ``config.layout.page_size`` — the config value is just a hint for authors;
  the PDF itself is the source of truth.
- Unknown values are skipped silently (makes field_name dicts forgiving).
- Empty / None values are skipped (don't draw blanks over the template).
- Wrapping is naive (splits on word boundaries, hard-wraps by char count).
  Real text measurement belongs in a later phase if we need justification.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from PyPDF2 import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

from luonvuitoi_cert.config import CertConfig, LayoutField
from luonvuitoi_cert.engine.fonts import FontRegistry


class OverlayError(Exception):
    """Raised when a rendering request can't be fulfilled (missing template, bad page)."""


@dataclass(slots=True)
class OverlayRequest:
    """All inputs the renderer needs to produce one certificate page."""

    config: CertConfig
    project_root: Path
    round_id: str
    page_number: int
    """1-indexed page number inside the round's template PDF."""
    values: dict[str, str] = field(default_factory=dict)
    """Field name → text to draw. Keys must match ``config.layout.fields``."""


def _resolve_template(request: OverlayRequest) -> Path:
    for r in request.config.rounds:
        if r.id == request.round_id:
            path = (request.project_root / r.pdf).resolve()
            if not path.exists():
                raise OverlayError(f"template PDF missing: {path} (round={r.id!r})")
            return path
    raise OverlayError(
        f"round_id {request.round_id!r} not found in config.rounds "
        f"(available: {[r.id for r in request.config.rounds]})"
    )


def _draw_text(c: canvas.Canvas, text: str, spec: LayoutField) -> None:
    """Render one field with the configured alignment + wrapping."""
    lines = textwrap.wrap(text, width=spec.wrap) if spec.wrap else [text]
    line_height = spec.size * 1.2
    # Multiline: draw first line at spec.y, subsequent lines below (descending y).
    for i, line in enumerate(lines):
        y = spec.y - i * line_height
        if spec.align == "center":
            c.drawCentredString(spec.x, y, line)
        elif spec.align == "right":
            c.drawRightString(spec.x, y, line)
        else:
            c.drawString(spec.x, y, line)


def render_certificate_bytes(
    request: OverlayRequest,
    font_registry: FontRegistry | None = None,
) -> bytes:
    """Return a one-page PDF with ``request.values`` drawn over the template page.

    If ``font_registry`` is None, a fresh one is constructed from the request's
    config + project_root. Reuse registries across requests (they're
    process-local caches) to avoid re-parsing TTF files.
    """
    template_path = _resolve_template(request)
    reader = PdfReader(str(template_path))
    if request.page_number < 1 or request.page_number > len(reader.pages):
        raise OverlayError(
            f"page_number {request.page_number} out of range for {template_path.name} "
            f"(1..{len(reader.pages)})"
        )
    template_page = reader.pages[request.page_number - 1]
    pw = float(template_page.mediabox.width)
    ph = float(template_page.mediabox.height)

    fonts = font_registry or FontRegistry(request.config, request.project_root)
    overlay_buf = BytesIO()
    c = canvas.Canvas(overlay_buf, pagesize=(pw, ph))

    for field_name, value in request.values.items():
        spec = request.config.layout.fields.get(field_name)
        if spec is None or value is None or value == "":
            continue
        psname = fonts.ensure_loaded(spec.font)
        c.setFont(psname, spec.size)
        c.setFillColor(HexColor(spec.color))
        _draw_text(c, str(value), spec)

    c.showPage()
    c.save()
    overlay_buf.seek(0)

    overlay_page = PdfReader(overlay_buf).pages[0]
    template_page.merge_page(overlay_page)
    writer = PdfWriter()
    writer.add_page(template_page)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()
