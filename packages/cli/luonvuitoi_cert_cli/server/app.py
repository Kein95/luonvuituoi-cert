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
import secrets
from dataclasses import asdict, is_dataclass
from pathlib import Path

from flask import Flask, Response, g, jsonify, make_response, request
from luonvuitoi_cert import api as handlers
from luonvuitoi_cert.api.admin_update import AdminUpdateError
from luonvuitoi_cert.api.security import get_allowed_origins
from luonvuitoi_cert.auth import (
    ActivityLog,
    AdminUserError,
    EmailError,
    LoginError,
    NullEmailProvider,
    ResendProvider,
    perform_login,
)
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
CAPTCHA_RATE_LIMIT = 30
CAPTCHA_RATE_WINDOW_SECONDS = 60


def _trust_proxy_headers() -> bool:
    """Whether the deploy sits behind a trusted reverse proxy.

    H5 fix: blindly reading ``X-Forwarded-For`` lets a direct client spoof
    their IP for rate-limit buckets. Only trust the header when the operator
    has set ``TRUST_PROXY_HEADERS=1`` (meaning they deployed behind Nginx /
    Caddy / Vercel / a known LB that overwrites the header).
    """
    return os.getenv("TRUST_PROXY_HEADERS", "").strip().lower() in {"1", "true", "yes"}


def _client_id() -> str:
    if _trust_proxy_headers():
        fwd = request.headers.get("X-Forwarded-For", "")
        if fwd:
            return fwd.split(",")[0].strip() or (request.remote_addr or "anon")
    return request.remote_addr or "anon"


def _resolve_email_provider():  # type: ignore[no-untyped-def]
    """Pick a real mailer when credentials are present; fall back to Null otherwise.

    C3 fix: ``build_app`` previously hard-coded ``NullEmailProvider`` which meant
    production Docker deploys silently dropped every OTP / magic-link message
    even with ``RESEND_API_KEY`` set. Now we inspect env and only fall back to
    Null when the key is missing, logging a warning so operators notice.
    """
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    # Accept both RESEND_FROM_ADDRESS and the .env.example variable CERT_EMAIL_FROM.
    from_addr = os.getenv("RESEND_FROM_ADDRESS", "").strip() or os.getenv("CERT_EMAIL_FROM", "").strip()
    if not api_key:
        _LOGGER.warning(
            "RESEND_API_KEY not set — OTP / magic-link emails will be swallowed. "
            "Set RESEND_API_KEY + RESEND_FROM_ADDRESS for production.",
        )
        return NullEmailProvider()
    if not from_addr:
        _LOGGER.warning(
            "RESEND_FROM_ADDRESS not set — falling back to NullEmailProvider. "
            "Set a verified Resend sender address to enable real delivery.",
        )
        return NullEmailProvider()
    try:
        return ResendProvider(api_key=api_key, from_address=from_addr)
    except EmailError as e:
        _LOGGER.warning("ResendProvider init failed (%s) — using NullEmailProvider.", e)
        return NullEmailProvider()


def _public_base_url() -> str:
    """Prefer explicit PUBLIC_BASE_URL over the attacker-controllable Host header.

    Phase 11 review H5: using ``request.host_url`` bakes whatever the client
    claimed the Host was into magic-link emails and printed QR codes. Operators
    set ``PUBLIC_BASE_URL`` in .env to pin the trusted origin; the dev
    fallback still uses ``request.host_url`` because localhost is trusted.
    """
    explicit = os.getenv("PUBLIC_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    return request.host_url.rstrip("/")


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
    mailer = _resolve_email_provider()

    app = Flask(__name__, static_folder=None)
    # H1: Werkzeug enforces this cap *before* parsing — a 1 GB POST is rejected
    # at the socket without the handler ever seeing it.
    app.config["MAX_CONTENT_LENGTH"] = MAX_BODY_BYTES

    @app.before_request
    def _assign_csp_nonce() -> None:  # type: ignore[no-untyped-def]
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.context_processor
    def _inject_nonce():  # type: ignore[no-untyped-def]
        return {"csp_nonce": g.csp_nonce}

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

    @app.errorhandler(handlers.VerifyError)
    def _verify(e):  # type: ignore[no-untyped-def]
        return jsonify({"error": str(e)}), 501

    @app.errorhandler(handlers.ShipmentHandlerError)
    def _ship(e):  # type: ignore[no-untyped-def]
        return jsonify({"error": str(e)}), 400

    @app.errorhandler(AdminUpdateError)
    def _admin_update(e):  # type: ignore[no-untyped-def]
        return jsonify({"error": str(e)}), 400

    @app.errorhandler(AdminUserError)
    def _admin_user(e):  # type: ignore[no-untyped-def]
        return jsonify({"error": str(e)}), 400

    # ── Pages ─────────────────────────────────────────────────────────
    @app.get("/")
    def _portal():  # type: ignore[no-untyped-def]
        return render_student_portal_page(config=config, locale=locale, csp_nonce=g.csp_nonce)

    @app.get("/admin")
    def _admin():  # type: ignore[no-untyped-def]
        return render_admin_page(config=config, locale=locale, csp_nonce=g.csp_nonce)

    @app.get("/certificate-checker")
    def _checker():  # type: ignore[no-untyped-def]
        return render_certificate_checker_page(config=config, locale=locale, csp_nonce=g.csp_nonce)

    # ── API ───────────────────────────────────────────────────────────
    @app.post("/api/captcha")
    def _captcha_issue():  # type: ignore[no-untyped-def]
        # C2 fix: gate challenge minting so a bot can't fill the KV with
        # 300s-TTL entries unbounded (KV quota/memory DoS, pay-per-request bill).
        handlers.check_rate_limit(
            kv,
            "captcha",
            _client_id(),
            limit=CAPTCHA_RATE_LIMIT,
            window_seconds=CAPTCHA_RATE_WINDOW_SECONDS,
        )
        ch = handlers.issue_challenge(kv)
        return jsonify({"id": ch.id, "question": ch.question})

    @app.post("/api/search")
    def _search_student():  # type: ignore[no-untyped-def]
        params = _json_body()
        mode = "admin" if params.get("mode") == "admin" else "student"
        result = handlers.search_student(
            config=config, db_path=db_path, kv=kv, params=params, client_id=_client_id(), mode=mode
        )
        return jsonify(
            {
                "sbd": result.sbd,
                "name": result.name,
                "fields": result.fields,
                "certificates": [_to_jsonable(c) for c in result.certificates],
            }
        )

    @app.post("/api/download")
    def _download():  # type: ignore[no-untyped-def]
        params = _json_body()
        mode = "admin" if params.get("mode") == "admin" else "student"
        base = _public_base_url()
        resp_obj = handlers.download_certificate(
            config=config,
            project_root=project_root,
            db_path=db_path,
            kv=kv,
            params=params,
            client_id=_client_id(),
            mode=mode,
            verify_url_builder=lambda blob: f"{base}/certificate-checker?blob={blob}",
        )
        flask_resp: Response = make_response(resp_obj.pdf_bytes)
        flask_resp.headers["Content-Type"] = resp_obj.content_type
        flask_resp.headers["Content-Disposition"] = f'attachment; filename="{resp_obj.filename}"'
        return flask_resp

    @app.post("/api/verify")
    def _verify_qr():  # type: ignore[no-untyped-def]
        params = _json_body()
        resp = handlers.verify_qr(config=config, project_root=project_root, blob=str(params.get("blob", "")))
        return jsonify(resp.to_json_safe())

    @app.post("/api/admin/login")
    def _login():  # type: ignore[no-untyped-def]
        params = _json_body()
        base = _public_base_url()
        try:
            result = perform_login(
                config,
                db_path=db_path,
                kv=kv,
                email_provider=mailer,
                params=params,
                activity=activity,
                ip=_client_id(),
                magic_link_builder=lambda token: f"{base}/admin?token={token}",
            )
        except LoginError as e:
            # H2: narrow exception — internal exceptions bubble to Flask's
            # default 500 (and get logged) rather than leaking to the client.
            return jsonify({"error": str(e)}), 401
        return jsonify({"token": result.token, "challenge_issued": result.challenge_issued})

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

    @app.before_request
    def _cors_preflight():  # type: ignore[no-untyped-def]
        # C1 fix: handle OPTIONS preflight for /api/* before route matching so
        # cross-origin browsers can probe without seeing a 405.
        if request.method != "OPTIONS" or not request.path.startswith("/api/"):
            return None
        resp = make_response("", 204)
        _apply_cors_headers(resp)
        return resp

    def _apply_cors_headers(response: Response) -> None:  # type: ignore[no-untyped-def]
        """Echo a single allowed origin back, per ALLOWED_ORIGINS env config.

        C1 fix: previously the app advertised CORS support in its docstring but
        never emitted a single ``Access-Control-Allow-*`` header. We now read
        ``ALLOWED_ORIGINS`` (comma-separated, or ``*`` wildcard) and echo the
        caller's ``Origin`` back when it matches — never credentials, never ``*``
        with ``Allow-Credentials: true`` (invalid combo per spec).
        """
        origin = request.headers.get("Origin", "")
        if not origin:
            return
        allowed = get_allowed_origins()
        if "*" in allowed:
            response.headers["Access-Control-Allow-Origin"] = "*"
        elif origin in allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers.setdefault("Vary", "Origin")
        else:
            return
        response.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        response.headers.setdefault("Access-Control-Allow-Headers", "Content-Type, Authorization")
        response.headers.setdefault("Access-Control-Max-Age", "600")

    @app.after_request
    def _security_headers(response: Response) -> Response:  # type: ignore[no-untyped-def]
        if request.path == "/admin":
            # H4: nonce-based CSP — inline scripts in admin.html.j2 carry the
            # same nonce, but a reflected-XSS injection point can't match it
            # without knowing the per-request value.
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                f"script-src 'self' 'nonce-{g.csp_nonce}'; "
                "style-src 'self' 'unsafe-inline'; "
                "frame-ancestors 'none'"
            )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.path.startswith("/api/"):
            _apply_cors_headers(response)
        return response

    return app
