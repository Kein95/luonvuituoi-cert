"""E2E regression tests for the P0 security fixes (C1, C2, C3).

These tests pin the behavior so the next refactor can't silently revert them:

- **C1**: CORS headers are wired when ``ALLOWED_ORIGINS`` is set, including
  OPTIONS preflight handling for ``/api/*`` routes.
- **C2**: ``/api/captcha`` is rate-limited — a burst of requests eventually
  returns 429 instead of unbounded KV writes.
- **C3**: ``build_app`` resolves a real mailer when ``RESEND_API_KEY`` is set
  and falls back to ``NullEmailProvider`` with a warning otherwise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


# ── C1: CORS wiring ──────────────────────────────────────────────────────────


def test_cors_preflight_returns_204_with_allowed_origin(
    monkeypatch: pytest.MonkeyPatch, scaffolded_project: Path
) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://trusted.example")
    from luonvuitoi_cert_cli.server import build_app
    from werkzeug.test import Client

    app = build_app(scaffolded_project / "cert.config.json", scaffolded_project)
    client = Client(app)
    resp = client.options(
        "/api/search",
        headers={
            "Origin": "https://trusted.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 204
    assert resp.headers["Access-Control-Allow-Origin"] == "https://trusted.example"
    assert "POST" in resp.headers.get("Access-Control-Allow-Methods", "")


def test_cors_echoes_only_allowed_origins(monkeypatch: pytest.MonkeyPatch, scaffolded_project: Path) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://trusted.example")
    from luonvuitoi_cert_cli.server import build_app
    from werkzeug.test import Client

    app = build_app(scaffolded_project / "cert.config.json", scaffolded_project)
    client = Client(app)
    resp = client.post(
        "/api/captcha",
        headers={"Origin": "https://evil.example"},
    )
    assert "Access-Control-Allow-Origin" not in resp.headers


def test_cors_wildcard_when_origins_env_unset(
    monkeypatch: pytest.MonkeyPatch, scaffolded_project: Path
) -> None:
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    from luonvuitoi_cert_cli.server import build_app
    from werkzeug.test import Client

    app = build_app(scaffolded_project / "cert.config.json", scaffolded_project)
    client = Client(app)
    resp = client.post("/api/captcha", headers={"Origin": "https://anywhere.example"})
    assert resp.headers.get("Access-Control-Allow-Origin") == "*"


# ── C2: captcha rate limit ───────────────────────────────────────────────────


def test_captcha_endpoint_is_rate_limited(monkeypatch: pytest.MonkeyPatch, scaffolded_project: Path) -> None:
    """31 rapid POSTs from the same IP must eventually be rejected with 429."""
    # Keep the rate-limit default (30/min) so we don't over-loop.
    from luonvuitoi_cert_cli.server import build_app
    from werkzeug.test import Client

    app = build_app(scaffolded_project / "cert.config.json", scaffolded_project)
    client = Client(app)

    codes: list[int] = []
    for _ in range(40):
        resp = client.post("/api/captcha", headers={"X-Forwarded-For": "10.0.0.1"})
        codes.append(resp.status_code)
        if resp.status_code == 429:
            break

    assert 429 in codes, f"expected a 429 within 40 reqs, got codes={codes!r}"


# ── C3: email provider resolution ────────────────────────────────────────────


def test_email_provider_falls_back_to_null_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    from luonvuitoi_cert.auth import NullEmailProvider
    from luonvuitoi_cert_cli.server.app import _resolve_email_provider

    provider = _resolve_email_provider()
    assert isinstance(provider, NullEmailProvider)


def test_email_provider_uses_resend_when_credentials_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM_ADDRESS", "ci@test.example")
    from luonvuitoi_cert.auth import ResendProvider
    from luonvuitoi_cert_cli.server.app import _resolve_email_provider

    provider = _resolve_email_provider()
    assert isinstance(provider, ResendProvider)


def test_email_provider_honors_cert_email_from_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CERT_EMAIL_FROM (per .env.example) must be accepted as a from-address."""
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.delenv("RESEND_FROM_ADDRESS", raising=False)
    monkeypatch.setenv("CERT_EMAIL_FROM", "alias@test.example")
    from luonvuitoi_cert.auth import ResendProvider
    from luonvuitoi_cert_cli.server.app import _resolve_email_provider

    provider = _resolve_email_provider()
    assert isinstance(provider, ResendProvider)


def test_email_provider_falls_back_when_from_address_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.delenv("RESEND_FROM_ADDRESS", raising=False)
    monkeypatch.delenv("CERT_EMAIL_FROM", raising=False)
    from luonvuitoi_cert.auth import NullEmailProvider
    from luonvuitoi_cert_cli.server.app import _resolve_email_provider

    provider = _resolve_email_provider()
    assert isinstance(provider, NullEmailProvider)
