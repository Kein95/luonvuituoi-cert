"""End-to-end: student portal search + download + QR verify against a live Flask server."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.e2e


def test_homepage_returns_student_portal(live_server: str) -> None:
    resp = httpx.get(live_server + "/")
    assert resp.status_code == 200
    assert "Certificate Portal" in resp.text
    # Three search-mode variants share one form; this config uses name_dob_captcha.
    assert 'id="dob"' in resp.text


def test_certificate_checker_page_served(live_server: str) -> None:
    resp = httpx.get(live_server + "/certificate-checker")
    assert resp.status_code == 200
    assert "Certificate Verification" in resp.text


def test_admin_page_has_csp_header(live_server: str) -> None:
    resp = httpx.get(live_server + "/admin")
    assert resp.status_code == 200
    assert "Content-Security-Policy" in resp.headers
    csp = resp.headers["Content-Security-Policy"]
    assert "'unsafe-inline'" not in csp.split("script-src", 1)[1].split(";", 1)[0]


def test_search_flow_finds_seeded_student(live_server: str, captcha_solver) -> None:  # type: ignore[no-untyped-def]
    challenge = captcha_solver(live_server)
    resp = httpx.post(
        live_server + "/api/search",
        json={
            "sbd": "12345",
            "name": "Alice Example",
            "dob": "01-06-2010",
            **challenge,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sbd"] == "12345"
    assert body["name"] == "Alice Example"
    assert any(c["round_id"] == "main" for c in body["certificates"])


def test_search_rate_limit_kicks_in(live_server: str, captcha_solver) -> None:  # type: ignore[no-untyped-def]
    """T1: loop until 429 with enough headroom that a cross-window-boundary
    roll-over won't flake. The fixed-window limiter resets at 60s ticks; if the
    first batch lands 59.9s into a window, req #21 arrives after rollover and
    comes back 200 — so the previous hard-coded "exactly 21 reqs" was timing-
    sensitive. Cap at 2× the limit (40 reqs) and assert *some* 429 appears.
    """
    codes: list[int] = []
    for _ in range(42):  # 2× STUDENT_RATE_LIMIT (20) + 2 buffer
        resp = httpx.post(
            live_server + "/api/search",
            json={
                "sbd": "12345",
                "name": "Alice Example",
                "dob": "01-06-2010",
                **captcha_solver(live_server),
            },
        )
        codes.append(resp.status_code)
        if resp.status_code == 429:
            assert "Retry-After" in resp.headers
            break
    assert 429 in codes, f"expected a 429 within 42 reqs, got {codes!r}"


def test_download_emits_pdf_with_qr_and_verifies(
    live_server: str, captcha_solver, scaffolded_project: Path
) -> None:  # type: ignore[no-untyped-def]
    challenge = captcha_solver(live_server)
    resp = httpx.post(
        live_server + "/api/download",
        json={
            "sbd": "12345",
            "name": "Alice Example",
            "dob": "01-06-2010",
            "round_id": "main",
            "subject_code": "G",
            **challenge,
        },
    )
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")

    # The PDF embeds a QR whose text is a /certificate-checker?blob=... URL.
    # Extract the QR pixel data deterministically via pyzbar isn't available,
    # so instead exercise the /api/verify endpoint with a directly-built blob:
    from luonvuitoi_cert.qr import QRPayload, encode_blob, load_private_key, sign_payload

    payload = QRPayload(
        project_slug="e2e-demo",
        round_id="main",
        subject_code="G",
        result="GOLD",
        sbd="12345",
        issued_at=1_700_000_000,
    )
    sig = sign_payload(load_private_key(scaffolded_project / "private_key.pem"), payload)
    blob = encode_blob(payload, sig)

    verify = httpx.post(live_server + "/api/verify", json={"blob": blob})
    assert verify.status_code == 200
    body = verify.json()
    assert body["valid"] is True
    assert body["payload"]["sbd"] == "12345"


def test_verify_rejects_tampered_blob(live_server: str) -> None:
    resp = httpx.post(live_server + "/api/verify", json={"blob": "bogus.blob"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert body["reason"]


def test_oversize_body_rejected(live_server: str) -> None:
    """Regression: Phase 11 H1 — MAX_CONTENT_LENGTH enforced by Werkzeug."""
    huge = {"sbd": "x" * (40 * 1024)}
    resp = httpx.post(live_server + "/api/search", json=huge)
    assert resp.status_code == 413


def test_verify_url_honors_public_base_url(live_server: str, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Regression: Phase 11 H5 — magic-link / verify URLs pin to env-configured base."""
    # Fresh server with PUBLIC_BASE_URL set ahead of request.
    # (Re-using live_server; just confirm the env-read path is reachable.)
    import os

    os.environ["PUBLIC_BASE_URL"] = "https://trusted.example"
    try:
        # We don't fully exercise the magic-link email here; just confirm the
        # _public_base_url helper reads the env in request context.
        from luonvuitoi_cert_cli.server.app import _public_base_url
        from werkzeug.test import EnvironBuilder

        builder = EnvironBuilder(method="POST", path="/x", headers={"Host": "evil.example"})
        env = builder.get_environ()
        # Bind a request context so request.host_url doesn't crash (even though env wins).
        import flask

        app = flask.Flask(__name__)
        with app.test_request_context(environ_overrides=env):
            assert _public_base_url() == "https://trusted.example"
    finally:
        del os.environ["PUBLIC_BASE_URL"]
