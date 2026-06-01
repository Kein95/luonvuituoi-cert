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
    # Public lookup now requires the same identity factor as search (name + DOB
    # in the default mode) on top of the CAPTCHA — a guessable SBD alone won't do.
    lookup = httpx.post(
        live_server + "/api/shipment/lookup",
        json={
            "sbd": "12345",
            "round_id": "main",
            "name": "Alice Example",
            "dob": "01-06-2010",
            **captcha_solver(live_server),
        },
    )
    assert lookup.status_code == 200, lookup.text
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


def test_shipment_lookup_rejects_wrong_identity(live_server: str, captcha_solver) -> None:  # type: ignore[no-untyped-def]
    """Correct SBD but no valid identity factor must not reveal the record."""
    token = _login(live_server)
    httpx.post(
        live_server + "/api/shipment/upsert",
        json={"token": token, "sbd": "12345", "round_id": "main", "status": "shipped"},
    )
    # Wrong name, wrong phone, no DOB → every factor fails.
    resp = httpx.post(
        live_server + "/api/shipment/lookup",
        json={
            "sbd": "12345",
            "round_id": "main",
            "name": "Not Alice",
            "phone": "0000",
            **captcha_solver(live_server),
        },
    )
    assert resp.status_code == 400
    assert "no shipment" in resp.json()["error"]


def test_shipment_lookup_by_phone(live_server: str, captcha_solver) -> None:  # type: ignore[no-untyped-def]
    """Recipient can confirm identity by phone (last 4) instead of name."""
    token = _login(live_server)
    httpx.post(
        live_server + "/api/shipment/upsert",
        json={"token": token, "sbd": "12345", "round_id": "main", "status": "shipped"},
    )
    resp = httpx.post(
        live_server + "/api/shipment/lookup",
        json={"sbd": "12345", "round_id": "main", "phone": "4567", **captcha_solver(live_server)},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "shipped"


def test_admin_login_rate_limited(live_server: str) -> None:
    """The only public credential-guessing endpoint must throttle (429).

    The limiter is fixed-window on wall-clock minutes, so a burst can straddle
    a boundary and split across two counters. Sending well over 2x the limit
    guarantees at least one window exceeds it regardless of where the boundary
    falls, so we assert *some* response was throttled rather than the last one.
    """
    statuses = [
        httpx.post(
            live_server + "/api/admin/login",
            json={"email": "e2e@admin.test", "password": "wrong"},
        ).status_code
        for _ in range(25)
    ]
    assert 429 in statuses, statuses
    assert statuses.count(401) >= 10  # genuine attempts still processed up to the cap


def test_shipment_import_large_body_not_413(live_server: str) -> None:
    """Regression: a >32KB upload must reach the handler, not be 413'd by a global cap."""
    big_csv = b"sbd,phone,tracking_code\n" + b"1,0900000000,VN1\n" * 5000  # ~90 KB
    resp = httpx.post(
        live_server + "/api/admin/shipments/import",
        files={"file": ("carrier.csv", big_csv, "text/csv")},
        data={"token": "not-a-valid-token", "round_id": "main"},
    )
    # Pre-fix this 413'd on the 32KB global cap; now it reaches auth → 401.
    assert resp.status_code != 413
    assert resp.status_code == 401
