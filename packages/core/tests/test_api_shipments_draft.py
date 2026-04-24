"""Integration tests: draft + export API endpoints."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def _make_draft_project(tmp_path: Path) -> Path:
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
                    "extra_cols": ["ship_method"],
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
                                    "export_template": {
                                        "sbd": "Mã học viên",
                                        "phone": "SĐT",
                                        "address": "Địa chỉ nhận",
                                        "recipient": "Người nhận",
                                    },
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
                "ship_method": "CA_NHAN",
                "result": "GOLD",
            },
            {
                "sbd": "10002",
                "full_name": "Student B",
                "dob": "01-01-2010",
                "school": "S",
                "phone": "0901000002",
                "ship_method": "TRUONG",
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


def test_draft_add_via_api(tmp_path: Path) -> None:
    from luonvuitoi_cert_cli.server import build_app
    from werkzeug.test import Client

    root = _make_draft_project(tmp_path)
    app = build_app(root / "cert.config.json", root)
    client = Client(app)

    resp = client.post(
        "/api/admin/shipments/draft",
        json={
            "token": _admin_jwt(),
            "round_id": "main",
            "filters": {"ship_method": "CA_NHAN"},
        },
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.json["created"] == 1
    assert resp.json["drafts"][0]["sbd"] == "10001"


def test_draft_list_via_api(tmp_path: Path) -> None:
    from luonvuitoi_cert_cli.server import build_app
    from werkzeug.test import Client

    root = _make_draft_project(tmp_path)
    app = build_app(root / "cert.config.json", root)
    client = Client(app)

    client.post(
        "/api/admin/shipments/draft",
        json={
            "token": _admin_jwt(),
            "round_id": "main",
            "sbd_list": ["10001", "10002"],
        },
    )
    resp = client.post(
        "/api/admin/shipments/draft/list",
        json={"token": _admin_jwt(), "round_id": "main"},
    )
    assert resp.status_code == 200
    assert resp.json["count"] == 2


def test_draft_cancel_via_api(tmp_path: Path) -> None:
    from luonvuitoi_cert_cli.server import build_app
    from werkzeug.test import Client

    root = _make_draft_project(tmp_path)
    app = build_app(root / "cert.config.json", root)
    client = Client(app)

    created = client.post(
        "/api/admin/shipments/draft",
        json={
            "token": _admin_jwt(),
            "round_id": "main",
            "sbd_list": ["10001"],
        },
    )
    draft_id = created.json["drafts"][0]["id"]

    resp = client.post(
        "/api/admin/shipments/draft/cancel",
        json={"token": _admin_jwt(), "ids": [draft_id]},
    )
    assert resp.status_code == 200
    assert resp.json["cancelled"] == 1


def test_export_downloads_xlsx(tmp_path: Path) -> None:
    from luonvuitoi_cert_cli.server import build_app
    from werkzeug.test import Client

    root = _make_draft_project(tmp_path)
    app = build_app(root / "cert.config.json", root)
    client = Client(app)

    client.post(
        "/api/admin/shipments/draft",
        json={
            "token": _admin_jwt(),
            "round_id": "main",
            "sbd_list": ["10001", "10002"],
        },
    )
    resp = client.post(
        "/api/admin/shipments/export",
        json={"token": _admin_jwt(), "round_id": "main", "carrier": "viettel"},
    )
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert resp.headers["X-Shipment-Row-Count"] == "2"
    assert resp.get_data()[:2] == b"PK"  # xlsx is a zip
