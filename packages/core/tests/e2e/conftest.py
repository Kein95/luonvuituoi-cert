"""E2E fixtures: spin up a real Flask server on an ephemeral port.

Each test file gets a fresh scaffolded project + live HTTP server so tests
stay independent without the expense of a subprocess per test. Uses
``werkzeug.serving.make_server`` in a daemon thread — stays within the
pytest process so coverage data aggregates cleanly.
"""

from __future__ import annotations

import shutil
import sqlite3
import threading
from contextlib import closing
from pathlib import Path

import pytest
import reportlab
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from werkzeug.serving import make_server

try:
    from luonvuitoi_cert_cli.server import build_app
except ImportError:  # pragma: no cover — CLI isn't installed in some environments
    build_app = None  # type: ignore[assignment]


DEMO_CONFIG = {
    "$schema": "../../cert.schema.json",
    "project": {"name": "E2E DEMO", "slug": "e2e-demo", "locale": "en"},
    "rounds": [{"id": "main", "label": "E2E", "table": "students", "pdf": "templates/main.pdf"}],
    "subjects": [{"code": "G", "en": "General", "db_col": "result"}],
    "results": {"G": {"GOLD": 1}},
    "data_mapping": {
        "sbd_col": "sbd",
        "name_col": "full_name",
        "dob_col": "dob",
        "school_col": "school",
        "phone_col": "phone",
    },
    "layout": {
        "page_size": [842, 595],
        "fields": {"name": {"x": 421, "y": 330, "font": "serif", "size": 24, "align": "center"}},
    },
    "fonts": {"serif": "assets/fonts/serif.ttf"},
    "admin": {"auth_mode": "password", "multi_user": True},
    "features": {"qr_verify": {"enabled": True}, "shipment": {"enabled": True}, "kv_backend": "local"},
}


@pytest.fixture(scope="session")
def _vera_ttf() -> Path:
    return Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"


@pytest.fixture
def scaffolded_project(tmp_path: Path, _vera_ttf: Path) -> Path:
    """A complete, disk-backed demo project: config + font + template + keypair + seeded student."""
    import json

    from luonvuitoi_cert.config import load_config
    from luonvuitoi_cert.ingest import ingest_rows
    from reportlab.pdfgen import canvas

    root = tmp_path / "e2e-root"
    root.mkdir()

    (root / "assets" / "fonts").mkdir(parents=True)
    shutil.copy2(_vera_ttf, root / "assets" / "fonts" / "serif.ttf")

    (root / "templates").mkdir()
    template_pdf = root / "templates" / "main.pdf"
    c = canvas.Canvas(str(template_pdf), pagesize=(842, 595))
    c.drawString(100, 550, "E2E TEMPLATE PAGE 1")
    c.showPage()
    c.save()

    config_path = root / "cert.config.json"
    config_path.write_text(json.dumps(DEMO_CONFIG), encoding="utf-8")

    # RSA keypair for the QR signer (features.qr_verify.enabled = True).
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (root / "private_key.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    (root / "public_key.pem").write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )

    # Seed a known student so the search flow has something to find.
    cfg = load_config(config_path)
    db_path = root / "data" / "e2e-demo.db"
    db_path.parent.mkdir()
    ingest_rows(
        cfg,
        db_path,
        "main",
        [
            {
                "sbd": "12345",
                "full_name": "Alice Example",
                "dob": "01-06-2010",
                "school": "E2E High School",
                "phone": "0901234567",
                "result": "GOLD",
            }
        ],
    )
    # An admin user for admin-flow tests.
    from luonvuitoi_cert.auth import Role, create_admin_user

    create_admin_user(db_path, email="e2e@admin.test", role=Role.ADMIN, password="hunter2-long-enough")
    return root


@pytest.fixture
def live_server(scaffolded_project: Path):  # type: ignore[no-untyped-def]
    if build_app is None:
        pytest.skip("luonvuitoi_cert_cli not installed")
    app = build_app(scaffolded_project / "cert.config.json", scaffolded_project)
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="e2e-flask")
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        yield base_url
    finally:
        server.shutdown()
        thread.join(timeout=2.0)


@pytest.fixture
def captcha_solver():  # type: ignore[no-untyped-def]
    """Helper that issues + solves a CAPTCHA against the live server."""
    import re

    import httpx

    def _solve(base_url: str) -> dict[str, object]:
        resp = httpx.post(f"{base_url}/api/captcha")
        resp.raise_for_status()
        challenge = resp.json()
        a, op, b = re.match(r"(\d+)\s*([+\-×])\s*(\d+)", challenge["question"]).groups()  # type: ignore[union-attr]
        answer = {"+": int(a) + int(b), "-": int(a) - int(b), "×": int(a) * int(b)}[op]
        return {"captcha_id": challenge["id"], "captcha_answer": answer}

    return _solve


@pytest.fixture
def project_db(scaffolded_project: Path) -> Path:
    """Convenience accessor for the students DB created by ``scaffolded_project``."""
    return scaffolded_project / "data" / "e2e-demo.db"


@pytest.fixture
def db_row_count():  # type: ignore[no-untyped-def]
    """Helper: count rows in a table of the live project DB."""

    def _count(db_path: Path, table: str) -> int:
        with closing(sqlite3.connect(str(db_path))) as conn:
            return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])

    return _count
