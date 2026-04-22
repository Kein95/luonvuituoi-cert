"""End-to-end: admin login → authenticated SBD lookup → shipment upsert → public lookup."""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.e2e


def _login(base_url: str, email: str = "e2e@admin.test", password: str = "hunter2-long-enough") -> str:
    resp = httpx.post(base_url + "/api/admin/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json().get("token")
    assert token
    return token


def test_password_login_returns_token(live_server: str) -> None:
    token = _login(live_server)
    assert token.count(".") == 2  # JWT has three base64url segments


def test_login_wrong_password_rejected(live_server: str) -> None:
    resp = httpx.post(
        live_server + "/api/admin/login",
        json={"email": "e2e@admin.test", "password": "wrong"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "invalid credentials"


def test_login_missing_fields_narrow_error(live_server: str) -> None:
    """Regression: Phase 11 H2 — /api/admin/login only surfaces LoginError messages."""
    resp = httpx.post(live_server + "/api/admin/login", json={})
    assert resp.status_code == 401
    assert resp.json()["error"] == "email and password are required"


def test_admin_search_by_sbd(live_server: str) -> None:
    token = _login(live_server)
    resp = httpx.post(
        live_server + "/api/search",
        json={"mode": "admin", "token": token, "sbd": "12345"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sbd"] == "12345"
    assert body["name"] == "Alice Example"


def test_admin_search_invalid_jwt_rejected(live_server: str) -> None:
    resp = httpx.post(
        live_server + "/api/search",
        json={"mode": "admin", "token": "not-a-jwt", "sbd": "12345"},
    )
    # SecurityError → 400.
    assert resp.status_code == 400


def test_shipment_upsert_then_public_lookup(
    live_server: str,
    captcha_solver,  # type: ignore[no-untyped-def]
) -> None:
    token = _login(live_server)
    # Admin writes the shipment row.
    upsert = httpx.post(
        live_server + "/api/shipment/upsert",
        json={
            "token": token,
            "sbd": "12345",
            "round_id": "main",
            "status": "shipped",
            "updates": {"tracking_code": "VN-0001", "carrier": "GHN"},
        },
    )
    assert upsert.status_code == 200, upsert.text
    # Public lookup sees only status + updated_at (default empty public_fields).
    lookup = httpx.post(
        live_server + "/api/shipment/lookup",
        json={"sbd": "12345", "round_id": "main", **captcha_solver(live_server)},
    )
    assert lookup.status_code == 200
    body = lookup.json()
    assert body["status"] == "shipped"
    assert body["fields"] == {}  # no public_fields in the E2E config


def test_shipment_upsert_rejects_unknown_status(live_server: str) -> None:
    token = _login(live_server)
    resp = httpx.post(
        live_server + "/api/shipment/upsert",
        json={
            "token": token,
            "sbd": "12345",
            "round_id": "main",
            "status": "lost",
        },
    )
    assert resp.status_code == 400


def test_shipment_lookup_requires_captcha(live_server: str) -> None:
    """Missing CAPTCHA → CaptchaError → 400."""
    resp = httpx.post(
        live_server + "/api/shipment/lookup",
        json={"sbd": "12345", "round_id": "main"},
    )
    assert resp.status_code == 400
