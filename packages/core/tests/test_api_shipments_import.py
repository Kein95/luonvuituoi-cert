"""Integration tests: POST /api/admin/shipments/import multipart upload."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def _make_import_project(tmp_path: Path) -> Path:
    """Scaffold a project with shipment.import config + seeded students."""
    import reportlab
    from luonvuitoi_cert.config import load_config
    from luonvuitoi_cert.ingest import ingest_rows

    (tmp_path / "assets" / "fonts").mkdir(parents=True)
    (tmp_path / "assets" / "fonts" / "serif.ttf").write_bytes(
        (Path(reportlab.__file__).parent / "fonts" / "Vera.ttf").read_bytes()
    )
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "main.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    (tmp_path / "cert.config.json").write_text(
        json.dumps(
            {
                "project": {"name": "T", "slug": "t", "locale": "en"},
                "rounds": [{"id": "main", "label": "M", "table": "students", "pdf": "templates/main.pdf"}],
                "subjects": [{"code": "G", "en": "G", "db_col": "result"}],
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
                "features": {
                    "kv_backend": "local",
                    "shipment": {
                        "enabled": True,
                        "statuses": ["pending", "shipped", "delivered"],
                        "fields": ["tracking_code", "carrier"],
                        "import": {
                            "default": "viettel",
                            "profiles": {
                                "viettel": {
                                    "column_mapping": {
                                        "tracking_code": ["Mã vận đơn"],
                                        "phone": ["SĐT"],
                                        "status": ["Trạng thái"],
                                    },
                                    "success_keywords": ["GIAO THÀNH CÔNG"],
                                }
                            },
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config(tmp_path / "cert.config.json")
    db = tmp_path / "data" / "t.db"
    db.parent.mkdir()
    ingest_rows(
        cfg,
        db,
        "main",
        [
            {
                "sbd": "10001",
                "full_name": "Student A",
                "dob": "01-01-2010",
                "school": "S",
                "phone": "0901000001",
                "result": "GOLD",
            },
        ],
    )
    return tmp_path


def _admin_jwt() -> str:
    from luonvuitoi_cert.auth import Role, issue_admin_token

    return issue_admin_token(
        user_id="admin1",
        email="admin@test.co",
        role=Role.ADMIN,
        env={"JWT_SECRET": "pytest-default-secret-padded-32-bytes-min"},
    )


def _viewer_jwt() -> str:
    from luonvuitoi_cert.auth import Role, issue_admin_token

    return issue_admin_token(
        user_id="viewer1",
        email="viewer@test.co",
        role=Role.VIEWER,
        env={"JWT_SECRET": "pytest-default-secret-padded-32-bytes-min"},
    )


def _carrier_xlsx_bytes() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Mã vận đơn", "SĐT", "Trạng thái"])
    ws.append(["VN001", "0901000001", "GIAO THÀNH CÔNG"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_upload_rejected_without_token(tmp_path: Path) -> None:
    from luonvuitoi_cert_cli.server import build_app
    from werkzeug.test import Client

    root = _make_import_project(tmp_path)
    app = build_app(root / "cert.config.json", root)
    client = Client(app)

    resp = client.post(
        "/api/admin/shipments/import",
        data={"round_id": "main", "carrier": "viettel"},
    )
    assert resp.status_code == 401


def test_upload_rejected_for_viewer_role(tmp_path: Path) -> None:
    from luonvuitoi_cert_cli.server import build_app
    from werkzeug.test import Client

    root = _make_import_project(tmp_path)
    app = build_app(root / "cert.config.json", root)
    client = Client(app)

    resp = client.post(
        "/api/admin/shipments/import",
        data={
            "token": _viewer_jwt(),
            "round_id": "main",
            "carrier": "viettel",
            "file": (io.BytesIO(_carrier_xlsx_bytes()), "carrier.xlsx"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 403


def test_upload_missing_file_field(tmp_path: Path) -> None:
    from luonvuitoi_cert_cli.server import build_app
    from werkzeug.test import Client

    root = _make_import_project(tmp_path)
    app = build_app(root / "cert.config.json", root)
    client = Client(app)

    resp = client.post(
        "/api/admin/shipments/import",
        data={"token": _admin_jwt(), "round_id": "main", "carrier": "viettel"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert "file" in resp.json["error"]


def test_upload_rejects_unsupported_extension(tmp_path: Path) -> None:
    from luonvuitoi_cert_cli.server import build_app
    from werkzeug.test import Client

    root = _make_import_project(tmp_path)
    app = build_app(root / "cert.config.json", root)
    client = Client(app)

    resp = client.post(
        "/api/admin/shipments/import",
        data={
            "token": _admin_jwt(),
            "round_id": "main",
            "carrier": "viettel",
            "file": (io.BytesIO(b"fake"), "bad.txt"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert "unsupported" in resp.json["error"]


def test_upload_dry_run_returns_stats(tmp_path: Path) -> None:
    from luonvuitoi_cert_cli.server import build_app
    from werkzeug.test import Client

    root = _make_import_project(tmp_path)
    app = build_app(root / "cert.config.json", root)
    client = Client(app)

    resp = client.post(
        "/api/admin/shipments/import",
        data={
            "token": _admin_jwt(),
            "round_id": "main",
            "carrier": "viettel",
            "file": (io.BytesIO(_carrier_xlsx_bytes()), "carrier.xlsx"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.json["parsed"] == 1
    assert resp.json["matched_sbds"] == 1
    assert resp.json["committed"] is False
    assert resp.json["inserted"] == 0


def test_upload_commit_writes_db(tmp_path: Path) -> None:
    import sqlite3

    from luonvuitoi_cert_cli.server import build_app
    from werkzeug.test import Client

    root = _make_import_project(tmp_path)
    app = build_app(root / "cert.config.json", root)
    client = Client(app)

    resp = client.post(
        "/api/admin/shipments/import",
        data={
            "token": _admin_jwt(),
            "round_id": "main",
            "carrier": "viettel",
            "commit": "true",
            "file": (io.BytesIO(_carrier_xlsx_bytes()), "carrier.xlsx"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert resp.json["committed"] is True
    assert resp.json["inserted"] == 1

    with sqlite3.connect(root / "data" / "t.db") as conn:
        count = conn.execute("SELECT COUNT(*) FROM shipment_history").fetchone()[0]
    assert count == 1


def test_upload_rejects_oversize_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from luonvuitoi_cert_cli.server import build_app
    from werkzeug.test import Client

    monkeypatch.setenv("SHIPMENT_IMPORT_MAX_BYTES", "1024")  # 1 KB cap

    root = _make_import_project(tmp_path)
    app = build_app(root / "cert.config.json", root)
    client = Client(app)

    big = b"\x00" * 5000  # 5 KB exceeds cap
    resp = client.post(
        "/api/admin/shipments/import",
        data={
            "token": _admin_jwt(),
            "round_id": "main",
            "carrier": "viettel",
            "file": (io.BytesIO(big), "carrier.xlsx"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 413
