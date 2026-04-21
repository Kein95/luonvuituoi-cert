"""Tests for RestKV — protocol-level verification with httpx MockTransport.

We don't require a live Upstash/Vercel endpoint. The mock captures the
command arrays the adapter sends and returns canned Redis-style responses.
"""

from __future__ import annotations

import json

import httpx
import pytest

from luonvuitoi_cert.storage.kv import KVError, RestKV


def _make_kv(handler):  # type: ignore[no-untyped-def]
    transport = httpx.MockTransport(handler)
    kv = RestKV("http://mock", "secret", timeout=1.0)
    # Replace the internal client with one bound to the mock transport.
    kv._client.close()
    kv._client = httpx.Client(
        base_url="http://mock", headers={"Authorization": "Bearer secret"}, transport=transport
    )
    return kv


def test_get_roundtrip() -> None:
    seen: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"result": "hello"})

    kv = _make_kv(handler)
    assert kv.get("foo") == "hello"
    assert seen[-1] == ["GET", "foo"]


def test_get_returns_none_for_null_result() -> None:
    def handler(_):  # type: ignore[no-untyped-def]
        return httpx.Response(200, json={"result": None})

    kv = _make_kv(handler)
    assert kv.get("missing") is None


def test_set_with_ttl_sends_ex() -> None:
    seen: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"result": "OK"})

    kv = _make_kv(handler)
    kv.set("foo", "bar", ttl_seconds=30)
    assert seen[-1] == ["SET", "foo", "bar", "EX", "30"]


def test_set_without_ttl_omits_ex() -> None:
    seen: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"result": "OK"})

    kv = _make_kv(handler)
    kv.set("foo", "bar")
    assert seen[-1] == ["SET", "foo", "bar"]


def test_exists_true_false() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(200, json={"result": 1 if body[1] == "exists-key" else 0})

    kv = _make_kv(handler)
    assert kv.exists("exists-key") is True
    assert kv.exists("missing") is False


def test_http_error_wraps_in_kv_error() -> None:
    def handler(_):  # type: ignore[no-untyped-def]
        return httpx.Response(500, json={"error": "boom"})

    kv = _make_kv(handler)
    with pytest.raises(KVError, match="transport error|command error"):
        kv.get("foo")


def test_command_error_surface() -> None:
    def handler(_):  # type: ignore[no-untyped-def]
        return httpx.Response(200, json={"error": "WRONGTYPE"})

    kv = _make_kv(handler)
    with pytest.raises(KVError, match="WRONGTYPE"):
        kv.get("foo")


def test_non_json_response_wrapped_in_kv_error() -> None:
    """Regression: Phase 04 review H3 — json.JSONDecodeError used to leak through."""

    def handler(_):  # type: ignore[no-untyped-def]
        return httpx.Response(200, content=b"not actually json")

    kv = _make_kv(handler)
    with pytest.raises(KVError, match="non-JSON"):
        kv.get("foo")


def test_consume_uses_getdel() -> None:
    """Regression: Phase 05 review C1 — atomic single-use via Redis GETDEL."""
    seen: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"result": "value"})

    kv = _make_kv(handler)
    assert kv.consume("foo") == "value"
    assert seen[-1] == ["GETDEL", "foo"]


def test_consume_missing_returns_none() -> None:
    def handler(_):  # type: ignore[no-untyped-def]
        return httpx.Response(200, json={"result": None})

    kv = _make_kv(handler)
    assert kv.consume("absent") is None


def test_scan_prefix_paginates_until_cursor_zero() -> None:
    responses = iter(
        [
            httpx.Response(200, json={"result": ["5", ["a:1", "a:2"]]}),
            httpx.Response(200, json={"result": ["0", ["a:3"]]}),
        ]
    )

    def handler(_):  # type: ignore[no-untyped-def]
        return next(responses)

    kv = _make_kv(handler)
    keys = kv.scan_prefix("a:")
    assert keys == ["a:1", "a:2", "a:3"]


def test_from_upstash_env_missing_creds() -> None:
    with pytest.raises(KVError, match="UPSTASH_REDIS_REST_URL"):
        RestKV.from_upstash_env({})


def test_from_vercel_env_missing_creds() -> None:
    with pytest.raises(KVError, match="KV_REST_API_URL"):
        RestKV.from_vercel_env({})
