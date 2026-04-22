"""Regression tests for the P2 hardening batch (M3, M4, M5, M6 + headers)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

# ── M4: /health endpoint ─────────────────────────────────────────────────────


def test_health_endpoint_returns_200(tmp_path: Path) -> None:
    from werkzeug.test import Client

    _make_minimal_project(tmp_path)
    from luonvuitoi_cert_cli.server import build_app

    app = build_app(tmp_path / "cert.config.json", tmp_path)
    client = Client(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json == {"ok": True}


# ── P2 polish: security headers ──────────────────────────────────────────────


def test_x_frame_options_set_on_every_response(tmp_path: Path) -> None:
    from werkzeug.test import Client

    _make_minimal_project(tmp_path)
    from luonvuitoi_cert_cli.server import build_app

    app = build_app(tmp_path / "cert.config.json", tmp_path)
    client = Client(app)
    resp = client.get("/health")
    assert resp.headers["X-Frame-Options"] == "DENY"


def test_hsts_set_only_when_forced(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from werkzeug.test import Client

    _make_minimal_project(tmp_path)
    from luonvuitoi_cert_cli.server import build_app

    # Without FORCE_HSTS: no header.
    monkeypatch.delenv("FORCE_HSTS", raising=False)
    app = build_app(tmp_path / "cert.config.json", tmp_path)
    client = Client(app)
    assert "Strict-Transport-Security" not in client.get("/health").headers

    # With FORCE_HSTS=1: header set on the next request.
    monkeypatch.setenv("FORCE_HSTS", "1")
    app = build_app(tmp_path / "cert.config.json", tmp_path)
    client = Client(app)
    resp = client.get("/health")
    assert "max-age=31536000" in resp.headers.get("Strict-Transport-Security", "")


# ── M6: webhook URL scheme validation ────────────────────────────────────────


def test_activity_log_rejects_http_webhook(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    from luonvuitoi_cert.auth import ActivityLog

    caplog.set_level(logging.WARNING, logger="luonvuitoi_cert.auth.activity_log")
    log = ActivityLog(tmp_path / "audit.db", gsheet_webhook_url="http://internal.example/wh")
    assert log._webhook is None  # type: ignore[attr-defined]
    assert any("must be https://" in rec.message for rec in caplog.records)


def test_activity_log_accepts_https_webhook(tmp_path: Path) -> None:
    from luonvuitoi_cert.auth import ActivityLog

    log = ActivityLog(tmp_path / "audit.db", gsheet_webhook_url="https://hooks.example/wh")
    assert log._webhook == "https://hooks.example/wh"  # type: ignore[attr-defined]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_minimal_project(tmp_path: Path) -> None:
    import json

    import reportlab

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
                "rounds": [
                    {
                        "id": "main",
                        "label": "M",
                        "table": "students",
                        "pdf": "templates/main.pdf",
                    }
                ],
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
                    "fields": {
                        "name": {
                            "x": 421,
                            "y": 330,
                            "font": "serif",
                            "size": 24,
                            "align": "center",
                        }
                    },
                },
                "fonts": {"serif": "assets/fonts/serif.ttf"},
                "features": {"kv_backend": "local"},
            }
        ),
        encoding="utf-8",
    )
