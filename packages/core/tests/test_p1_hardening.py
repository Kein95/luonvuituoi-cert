"""Regression tests for the P1 hardening fixes (H2, H3, H4, H5).

- H2: ``open_kv`` logs a warning when ``KV_BACKEND=local`` and the host
  advertises >1 worker (gunicorn/uvicorn/waitress).
- H3: ``CertConfig.rounds`` is capped at 20 entries.
- H4: Activity-log webhook dispatch uses a bounded executor, not an
  unbounded daemon thread per call.
- H5: ``_client_id`` only honors ``X-Forwarded-For`` when
  ``TRUST_PROXY_HEADERS`` is truthy.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

# ── H2: LocalFileKV multi-worker warning ─────────────────────────────────────


def test_local_kv_warns_on_multiple_workers(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    from luonvuitoi_cert.config import load_config
    from luonvuitoi_cert.storage.kv import open_kv

    _make_minimal_config(tmp_path)
    cfg = load_config(tmp_path / "cert.config.json")

    caplog.set_level(logging.WARNING, logger="luonvuitoi_cert.storage.kv.factory")
    open_kv(cfg, tmp_path, env={"WEB_CONCURRENCY": "4"})
    assert any("KV_BACKEND=local with 4 workers is unsafe" in rec.message for rec in caplog.records), [
        rec.message for rec in caplog.records
    ]


def test_local_kv_silent_for_single_worker(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    from luonvuitoi_cert.config import load_config
    from luonvuitoi_cert.storage.kv import open_kv

    _make_minimal_config(tmp_path)
    cfg = load_config(tmp_path / "cert.config.json")

    caplog.set_level(logging.WARNING, logger="luonvuitoi_cert.storage.kv.factory")
    open_kv(cfg, tmp_path, env={"WEB_CONCURRENCY": "1"})
    open_kv(cfg, tmp_path, env={})  # nothing set → silent
    assert not any("unsafe" in rec.message for rec in caplog.records)


# ── H3: rounds upper bound ───────────────────────────────────────────────────


def test_rounds_capped_at_20(tmp_path: Path) -> None:
    from luonvuitoi_cert.config import load_config
    from luonvuitoi_cert.config.loader import ConfigError

    base = _minimal_config_payload()
    base["rounds"] = [
        {
            "id": f"r{i}",
            "label": f"Round {i}",
            "table": "students",
            "pdf": "templates/main.pdf",
        }
        for i in range(25)
    ]
    (tmp_path / "cert.config.json").write_text(json.dumps(base), encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path / "cert.config.json")
    assert "rounds" in str(exc.value)
    assert "at most 20" in str(exc.value)


def test_rounds_at_limit_still_loads(tmp_path: Path) -> None:
    from luonvuitoi_cert.config import load_config

    base = _minimal_config_payload()
    base["rounds"] = [
        {
            "id": f"r{i}",
            "label": f"Round {i}",
            "table": "students",
            "pdf": "templates/main.pdf",
        }
        for i in range(20)
    ]
    (tmp_path / "cert.config.json").write_text(json.dumps(base), encoding="utf-8")
    cfg = load_config(tmp_path / "cert.config.json")
    assert len(cfg.rounds) == 20


# ── H4: bounded executor ─────────────────────────────────────────────────────


def test_activity_log_webhook_uses_bounded_executor(tmp_path: Path) -> None:
    """The executor is a module-level singleton, not per-instance thread spawns."""
    from concurrent.futures import ThreadPoolExecutor

    from luonvuitoi_cert.auth.activity_log import _WEBHOOK_EXECUTOR

    assert isinstance(_WEBHOOK_EXECUTOR, ThreadPoolExecutor)
    assert _WEBHOOK_EXECUTOR._max_workers == 4  # type: ignore[attr-defined]


# ── H5: X-Forwarded-For opt-in ───────────────────────────────────────────────


def test_client_id_ignores_xff_without_trust_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("TRUST_PROXY_HEADERS", raising=False)
    _make_minimal_config(tmp_path)
    from luonvuitoi_cert_cli.server import build_app
    from werkzeug.test import Client

    app = build_app(tmp_path / "cert.config.json", tmp_path)

    @app.post("/_dbg/client_id")
    def _expose_client_id():  # type: ignore[no-untyped-def]
        from flask import jsonify
        from luonvuitoi_cert_cli.server.app import _client_id

        return jsonify({"client_id": _client_id()})

    client = Client(app)
    resp = client.post(
        "/_dbg/client_id",
        headers={"X-Forwarded-For": "1.2.3.4"},
        environ_overrides={"REMOTE_ADDR": "5.6.7.8"},
    )
    assert resp.json["client_id"] == "5.6.7.8"


def test_client_id_honors_xff_when_trusted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "1")
    _make_minimal_config(tmp_path)
    from luonvuitoi_cert_cli.server import build_app
    from werkzeug.test import Client

    app = build_app(tmp_path / "cert.config.json", tmp_path)

    @app.post("/_dbg/client_id")
    def _expose_client_id():  # type: ignore[no-untyped-def]
        from flask import jsonify
        from luonvuitoi_cert_cli.server.app import _client_id

        return jsonify({"client_id": _client_id()})

    client = Client(app)
    resp = client.post(
        "/_dbg/client_id",
        headers={"X-Forwarded-For": "1.2.3.4, 10.0.0.1"},
        environ_overrides={"REMOTE_ADDR": "5.6.7.8"},
    )
    assert resp.json["client_id"] == "1.2.3.4"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _minimal_config_payload() -> dict:
    return {
        "project": {"name": "T", "slug": "t", "locale": "en"},
        "rounds": [{"id": "main", "label": "Main", "table": "students", "pdf": "templates/main.pdf"}],
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
        "features": {"kv_backend": "local"},
    }


def _make_minimal_config(tmp_path: Path) -> None:
    """Write a minimal config + the referenced font file so ``load_config`` succeeds."""
    import reportlab

    (tmp_path / "assets" / "fonts").mkdir(parents=True)
    vera = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
    (tmp_path / "assets" / "fonts" / "serif.ttf").write_bytes(vera.read_bytes())
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "main.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    (tmp_path / "cert.config.json").write_text(json.dumps(_minimal_config_payload()), encoding="utf-8")
