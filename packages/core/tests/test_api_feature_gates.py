"""Integration tests: /api/admin/features + /api/admin/features/update + gated public endpoints."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def _make_project(tmp_path: Path) -> Path:
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
                    "phone_col": "phone",
                },
                "student_search": {"mode": "sbd_phone"},
                "layout": {
                    "page_size": [842, 595],
                    "fields": {"name": {"x": 421, "y": 330, "font": "serif", "size": 24, "align": "center"}},
                },
                "fonts": {"serif": "assets/fonts/serif.ttf"},
                "features": {"kv_backend": "local"},
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
                "phone": "0901000001",
                "result": "GOLD",
            },
        ],
    )
    return tmp_path


def _token(role: str) -> str:
    from luonvuitoi_cert.auth import Role, issue_admin_token

    return issue_admin_token(
        user_id="u1",
        email="u1@test.co",
        role=Role(role),
        env={"JWT_SECRET": "pytest-default-secret-padded-32-bytes-min"},
    )


def _client(tmp_path: Path):  # type: ignore[no-untyped-def]
    from luonvuitoi_cert_cli.server import build_app
    from werkzeug.test import Client

    root = _make_project(tmp_path)
    app = build_app(root / "cert.config.json", root)
    return Client(app), root


def test_read_defaults_both_on(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    resp = client.post("/api/admin/features", json={"token": _token("super-admin")})
    assert resp.status_code == 200
    assert resp.json == {"lookup_enabled": True, "download_enabled": True}


def test_read_requires_super_admin(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    resp = client.post("/api/admin/features", json={"token": _token("admin")})
    assert resp.status_code == 403
    assert "super-admin" in resp.json["error"]


def test_read_rejects_missing_token(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    resp = client.post("/api/admin/features", json={})
    assert resp.status_code == 401


def test_update_requires_super_admin(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    resp = client.post(
        "/api/admin/features/update",
        json={"token": _token("admin"), "lookup_enabled": False, "download_enabled": False},
    )
    assert resp.status_code == 403


def test_update_flip_lookup_off_clamps_download(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    resp = client.post(
        "/api/admin/features/update",
        json={"token": _token("super-admin"), "lookup_enabled": False, "download_enabled": True},
    )
    assert resp.status_code == 200
    assert resp.json == {"lookup_enabled": False, "download_enabled": False}


def test_update_lookup_on_download_off(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    resp = client.post(
        "/api/admin/features/update",
        json={"token": _token("super-admin"), "lookup_enabled": True, "download_enabled": False},
    )
    assert resp.status_code == 200
    assert resp.json == {"lookup_enabled": True, "download_enabled": False}


def test_search_returns_503_when_lookup_disabled(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    client.post(
        "/api/admin/features/update",
        json={"token": _token("super-admin"), "lookup_enabled": False, "download_enabled": False},
    )
    resp = client.post("/api/search", json={"sbd": "10001", "phone": "0901000001"})
    assert resp.status_code == 503
    assert "lookup" in resp.json["error"]


def test_search_passes_gate_when_lookup_enabled(tmp_path: Path) -> None:
    """Gate lets the request through — captcha layer takes over. A 503 would
    prove the gate fired; any other error means the gate passed and the
    request is handled by the usual pipeline.
    """
    client, _ = _client(tmp_path)
    # Default is enabled; no flip needed.
    resp = client.post("/api/search", json={"sbd": "10001", "phone": "0901000001"})
    assert resp.status_code != 503
    assert "lookup" not in str(resp.json.get("error", "")).lower()


def test_admin_search_bypasses_gate(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    # Freeze the public surface.
    client.post(
        "/api/admin/features/update",
        json={"token": _token("super-admin"), "lookup_enabled": False, "download_enabled": False},
    )
    # Admin mode must still work so operators can run the panel during a freeze.
    resp = client.post(
        "/api/search",
        json={"sbd": "10001", "mode": "admin", "token": _token("admin")},
    )
    assert resp.status_code == 200
    assert resp.json["sbd"] == "10001"


def test_download_returns_503_when_download_disabled(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    # Lookup on, download off — student can search but not download.
    client.post(
        "/api/admin/features/update",
        json={"token": _token("super-admin"), "lookup_enabled": True, "download_enabled": False},
    )
    resp = client.post(
        "/api/download",
        json={
            "sbd": "10001",
            "phone": "0901000001",
            "round_id": "main",
            "subject_code": "G",
        },
    )
    assert resp.status_code == 503
    assert "download" in resp.json["error"]


def test_download_returns_503_when_lookup_disabled(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    client.post(
        "/api/admin/features/update",
        json={"token": _token("super-admin"), "lookup_enabled": False, "download_enabled": False},
    )
    resp = client.post(
        "/api/download",
        json={
            "sbd": "10001",
            "phone": "0901000001",
            "round_id": "main",
            "subject_code": "G",
        },
    )
    assert resp.status_code == 503


def test_login_response_includes_role(tmp_path: Path) -> None:
    """UI needs the role to decide whether to render the feature-toggle card."""
    from luonvuitoi_cert.auth import Role, create_admin_user

    client, root = _client(tmp_path)
    db = root / "data" / "t.db"
    create_admin_user(
        db,
        email="super@test.co",
        password="pw-for-test-1234",
        role=Role.SUPER_ADMIN,
    )
    resp = client.post(
        "/api/admin/login",
        json={"email": "super@test.co", "password": "pw-for-test-1234"},
    )
    assert resp.status_code == 200
    assert resp.json["role"] == "super-admin"
    assert resp.json["token"]
