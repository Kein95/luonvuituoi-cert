"""Flask app builder for the local dev server.

Deliberately minimal: each route reads / parses the body, calls the matching
pure-function handler, and serializes the result. Everything the production
serverless handler would do (CORS, CSP, size caps) is also done here so dev
matches prod behavior within a single process.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, is_dataclass
from pathlib import Path

from flask import Flask, Response, jsonify, make_response, request

from luonvuitoi_cert import api as handlers
from luonvuitoi_cert.auth import ActivityLog, NullEmailProvider, perform_login
from luonvuitoi_cert.config import load_config
from luonvuitoi_cert.locale import load_locale
from luonvuitoi_cert.storage.kv import open_kv
from luonvuitoi_cert.ui import (
    render_admin_page,
    render_certificate_checker_page,
    render_student_portal_page,
)

_LOGGER = logging.getLogger(__name__)

MAX_BODY_BYTES = 32 * 1024


def _client_id() -> str:
    # Honor X-Forwarded-For when behind a proxy; dev uses remote_addr directly.
    fwd = request.headers.get("X-Forwarded-For", "")
    return (fwd.split(",")[0].strip() if fwd else request.remote_addr) or "anon"


def _json_body() -> dict:
    raw = request.get_data(cache=False) or b""
    handlers.validate_request_size(raw, max_bytes=MAX_BODY_BYTES)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise handlers.SecurityError(f"invalid JSON body: {e.msg}") from e
    if not isinstance(parsed, dict):
        raise handlers.SecurityError("request body must be a JSON object")
    return parsed


def _to_jsonable(value):  # type: ignore[no-untyped-def]
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    return value


def build_app(config_path: Path, project_root: Path) -> Flask:
    config = load_config(config_path)
    locale = load_locale(config.project.locale)
    kv = open_kv(config, project_root)
    db_path = project_root / "data" / f"{config.project.slug}.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    activity = ActivityLog(db_path, gsheet_webhook_url=os.getenv("GSHEET_WEBHOOK_URL"))
    mailer = NullEmailProvider()

    app = Flask(__name__, static_folder=None)

    # ── Error translators ─────────────────────────────────────────────
    @app.errorhandler(handlers.SecurityError)
    def _sec(e):  # type: ignore[no-untyped-def]
        return jsonify({"error": str(e)}), 400

    @app.errorhandler(handlers.RateLimitError)
    def _rl(e):  # type: ignore[no-untyped-def]
        resp = jsonify({"error": str(e)})
        resp.status_code = 429
        resp.headers["Retry-After"] = str(e.retry_after_seconds)
        return resp

    @app.errorhandler(handlers.SearchError)
    def _search(e):  # type: ignore[no-untyped-def]
        return jsonify({"error": str(e)}), 404

    @app.errorhandler(handlers.CaptchaError)
    def _captcha(e):  # type: ignore[no-untyped-def]
        return jsonify({"error": str(e)}), 400

    # ── Pages ─────────────────────────────────────────────────────────
    @app.get("/")
    def _portal():  # type: ignore[no-untyped-def]
        return render_student_portal_page(config=config, locale=locale)

    @app.get("/admin")
    def _admin():  # type: ignore[no-untyped-def]
        return render_admin_page(config=config, locale=locale)

    @app.get("/certificate-checker")
    def _checker():  # type: ignore[no-untyped-def]
        return render_certificate_checker_page(config=config, locale=locale)

    # ── API ───────────────────────────────────────────────────────────
    @app.post("/api/captcha")
    def _captcha_issue():  # type: ignore[no-untyped-def]
        ch = handlers.issue_challenge(kv)
        return jsonify({"id": ch.id, "question": ch.question})

    @app.post("/api/search")
    def _search_student():  # type: ignore[no-untyped-def]
        params = _json_body()
        mode = "admin" if params.get("mode") == "admin" else "student"
        result = handlers.search_student(
            config=config, db_path=db_path, kv=kv, params=params, client_id=_client_id(), mode=mode
        )
        return jsonify({
            "sbd": result.sbd,
            "name": result.name,
            "fields": result.fields,
            "certificates": [_to_jsonable(c) for c in result.certificates],
        })

    @app.post("/api/download")
    def _download():  # type: ignore[no-untyped-def]
        params = _json_body()
        mode = "admin" if params.get("mode") == "admin" else "student"
        resp_obj = handlers.download_certificate(
            config=config,
            project_root=project_root,
            db_path=db_path,
            kv=kv,
            params=params,
            client_id=_client_id(),
            mode=mode,
            verify_url_builder=lambda blob: request.host_url.rstrip("/") + f"/certificate-checker?blob={blob}",
        )
        flask_resp: Response = make_response(resp_obj.pdf_bytes)
        flask_resp.headers["Content-Type"] = resp_obj.content_type
        flask_resp.headers["Content-Disposition"] = f'attachment; filename="{resp_obj.filename}"'
        return flask_resp

    @app.post("/api/verify")
    def _verify():  # type: ignore[no-untyped-def]
        params = _json_body()
        resp = handlers.verify_qr(config=config, project_root=project_root, blob=str(params.get("blob", "")))
        return jsonify(resp.to_json_safe())

    @app.post("/api/admin/login")
    def _login():  # type: ignore[no-untyped-def]
        params = _json_body()
        try:
            result = perform_login(
                config,
                db_path=db_path,
                kv=kv,
                email_provider=mailer,
                params=params,
                activity=activity,
                ip=_client_id(),
                magic_link_builder=lambda token: request.host_url.rstrip("/") + f"/admin?token={token}",
            )
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 401
        return jsonify({"token": result.token, "challenge_issued": result.challenge_issued})

    # Admin mutations (shipment + student update) — protected by JWT in the handler itself.
    @app.post("/api/shipment/upsert")
    def _shipment_upsert():  # type: ignore[no-untyped-def]
        params = _json_body()
        rec = handlers.upsert_shipment_record(
            config=config, db_path=db_path, activity=activity, params=params, client_ip=_client_id()
        )
        return jsonify(asdict(rec))

    @app.post("/api/shipment/lookup")
    def _shipment_lookup():  # type: ignore[no-untyped-def]
        resp = handlers.lookup_shipment(
            config=config, db_path=db_path, kv=kv, params=_json_body(), client_id=_client_id()
        )
        return jsonify(asdict(resp))

    # CSP header for /admin so the sessionStorage JWT isn't one reflected-XSS
    # away from being exfiltrated.
    @app.after_request
    def _security_headers(response: Response) -> Response:  # type: ignore[no-untyped-def]
        if request.path == "/admin":
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    return app
