"""Bootstrap the demo-academy example.

Run once after ``pip install luonvuitoi-cert-cli`` to:

1. Copy Bitstream Vera (Apache-2.0) fonts from ReportLab's bundle into
   ``assets/fonts/{script,serif}.ttf``. Production projects should swap
   these for real script + serif faces; Vera renders cleanly enough for
   the demo to look plausible.
2. Generate a 2-page certificate template (Gold + Silver) at
   ``templates/main.pdf`` with reportlab so no binary PDF is checked in.
3. Seed ``data/students.xlsx`` with 10 fake students via ``lvt-cert seed``.

Idempotent: rerunning overwrites the generated artefacts.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import reportlab
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent
FONTS_DIR = ROOT / "assets" / "fonts"
TEMPLATES_DIR = ROOT / "templates"
DATA_DIR = ROOT / "data"

_VERA_SRC = Path(reportlab.__file__).parent / "fonts"


def copy_fonts() -> None:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    # Vera (Sans) for both script + serif slots — demo only; swap for real
    # typefaces when you customise the project.
    shutil.copy2(_VERA_SRC / "Vera.ttf", FONTS_DIR / "serif.ttf")
    shutil.copy2(_VERA_SRC / "VeraBI.ttf", FONTS_DIR / "script.ttf")


def render_template_pdf() -> None:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    target = TEMPLATES_DIR / "main.pdf"
    landscape_a5 = (842, 595)
    c = canvas.Canvas(str(target), pagesize=landscape_a5)
    for page_no, (tier, accent) in enumerate(
        [("GOLD", HexColor("#B68800")), ("SILVER", HexColor("#737373"))], start=1
    ):
        _draw_certificate_page(c, tier, accent, landscape_a5)
        c.showPage()
    c.save()
    print(f"  -> {target.relative_to(ROOT)}")


def _draw_certificate_page(c: canvas.Canvas, tier: str, accent, size) -> None:  # type: ignore[no-untyped-def]
    w, h = size
    # Decorative border.
    c.setStrokeColor(accent)
    c.setLineWidth(6)
    c.rect(30, 30, w - 60, h - 60)
    c.setLineWidth(2)
    c.rect(45, 45, w - 90, h - 90)

    # Header.
    c.setFillColor(HexColor("#1E3A8A"))
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(w / 2, h - 90, "DEMO ACADEMY")
    c.setFont("Helvetica", 11)
    c.drawCentredString(w / 2, h - 108, "Certificate of Achievement")

    # Tier medallion.
    c.setFillColor(accent)
    c.circle(w / 2, h - 160, 22, fill=1, stroke=0)
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(w / 2, h - 164, tier)

    # Caption line above the (overlaid) student name.
    c.setFillColor(HexColor("#334155"))
    c.setFont("Helvetica", 12)
    c.drawCentredString(w / 2, 380, "This certificate is awarded to")

    # Bottom caption below the (overlaid) school line.
    c.setFillColor(HexColor("#475569"))
    c.setFont("Helvetica-Oblique", 11)
    c.drawCentredString(
        w / 2,
        230,
        f"for demonstrating excellence in the DEMO ACADEMY — {tier.title()} Tier.",
    )
    c.drawCentredString(w / 2, 210, "Issued on the date of download.")

    # Signature line.
    c.setStrokeColor(HexColor("#1E3A8A"))
    c.setLineWidth(1)
    c.line(w / 2 - 120, 130, w / 2 + 120, 130)
    c.setFont("Helvetica", 10)
    c.drawCentredString(w / 2, 115, "Director of Achievement")


def seed_students() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output = DATA_DIR / "students.xlsx"
    cmd = [
        sys.executable,
        "-m",
        "luonvuitoi_cert_cli.main",
        "seed",
        "--count",
        "10",
        "--seed",
        "42",
        "--output",
        str(output),
        "--config",
        str(ROOT / "cert.config.json"),
    ]
    subprocess.check_call(cmd)


def main() -> int:
    print("demo-academy: preparing assets...")
    copy_fonts()
    print(f"  -> fonts under {FONTS_DIR.relative_to(ROOT)}")
    render_template_pdf()
    seed_students()
    print(
        "\nDone. Next:"
        "\n  lvt-cert gen-keys         # only needed because features.qr_verify.enabled = true"
        "\n  cp .env.example .env      # set JWT_SECRET to something random + 32 chars"
        "\n  lvt-cert dev              # open http://127.0.0.1:5000"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
