"""End-to-end tests for the ``GET /static/<name>`` dispatcher route.

The reader-level tests in core (``test_static_assets.py``) cover the lookup
helper; these exercise the actual Flask route through ``build_app`` so the
HTTP-layer concerns (status codes, headers, traversal-via-URL) get coverage.

Uses the same scaffolded project fixture pattern as the core e2e suite so the
tests don't need a curated config bundled with the test data.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import reportlab
from luonvuitoi_cert_cli.server import build_app
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas

_REPORTLAB_FONTS = Path(reportlab.__file__).parent / "fonts"


def _build_minimal_project(tmp_path: Path) -> Path:
    """Write the smallest valid scaffold: cert.config.json + font + template PDF."""
    (tmp_path / "assets" / "fonts").mkdir(parents=True)
    (tmp_path / "templates").mkdir()
    # Copy a TTF reportlab ships with (Apache-2.0).
    import shutil

    shutil.copy2(_REPORTLAB_FONTS / "Vera.ttf", tmp_path / "assets" / "fonts" / "serif.ttf")

    # Two-page placeholder PDF.
    writer = PdfWriter()
    for label in ("GOLD", "SILVER"):
        scratch = tmp_path / f"_page_{label}.pdf"
        c = rl_canvas.Canvas(str(scratch), pagesize=A4)
        c.drawString(100, 750, label)
        c.showPage()
        c.save()
        writer.add_page(PdfReader(str(scratch)).pages[0])
    with (tmp_path / "templates" / "main.pdf").open("wb") as f:
        writer.write(f)

    cfg = {
        "project": {"name": "Static Probe", "slug": "static-probe", "locale": "en"},
        "rounds": [{"id": "main", "label": "Main", "table": "students", "pdf": "templates/main.pdf"}],
        "subjects": [{"code": "S", "en": "Science", "db_col": "s"}],
        "results": {"S": {"GOLD": 1, "SILVER": 2}},
        "data_mapping": {
            "sbd_col": "sbd",
            "name_col": "full_name",
            "dob_col": "dob",
            "school_col": "school",
            "phone_col": "phone",
        },
        "layout": {
            "page_size": [842, 595],
            "fields": {"name": {"x": 421, "y": 400, "font": "serif", "size": 24, "align": "center"}},
        },
        "fonts": {"serif": "assets/fonts/serif.ttf"},
    }
    (tmp_path / "cert.config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("JWT_SECRET", "test-secret-padded-to-32-bytes-min__")
    project_root = _build_minimal_project(tmp_path)
    app = build_app(project_root / "cert.config.json", project_root)
    app.testing = True
    return app.test_client()


def test_static_serves_qr_decode_helper(client) -> None:  # type: ignore[no-untyped-def]
    resp = client.get("/static/qr-decode-helper.js")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "application/javascript"
    assert resp.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    assert b"window.LvtQR" in resp.data


def test_static_unknown_file_404(client) -> None:  # type: ignore[no-untyped-def]
    resp = client.get("/static/does-not-exist.js")
    assert resp.status_code == 404
    assert resp.is_json
    assert "error" in resp.get_json()


def test_static_unknown_suffix_404(client) -> None:  # type: ignore[no-untyped-def]
    """Suffix allowlist is enforced — even if the name regex passed, .html is rejected."""
    resp = client.get("/static/index.html")
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "name",
    [
        "..",
        "..%2Fconfig%2Fmodels.py",
        "%2e%2e%2fpages.py",
        "subdir%2Ffile.js",
        ".hidden.js",
        "name with space.js",
    ],
)
def test_static_traversal_blocked(client, name: str) -> None:  # type: ignore[no-untyped-def]
    """Werkzeug decodes %xx before our regex sees it; encoded slashes still fail validation."""
    resp = client.get(f"/static/{name}")
    assert resp.status_code in (400, 404), (name, resp.status_code, resp.data[:200])


def test_certificate_checker_renders_static_url(client) -> None:  # type: ignore[no-untyped-def]
    """Verifier page references both vendored scripts under /static."""
    resp = client.get("/certificate-checker")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "/static/jsqr.min.js" in body
    assert "/static/qr-decode-helper.js" in body
