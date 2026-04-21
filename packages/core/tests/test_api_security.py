"""Tests for :mod:`luonvuitoi_cert.api.security`."""

from __future__ import annotations

import os

import pytest

from luonvuitoi_cert.api.security import (
    DEFAULT_ALLOWED_ORIGINS,
    MAX_REQUEST_BYTES_DEFAULT,
    SecurityError,
    clean_sbd,
    get_allowed_origins,
    sanitize_filename,
    validate_request_size,
    validate_sbd,
)


# ── clean_sbd ───────────────────────────────────────────────────────


def test_clean_sbd_strips_float_suffix() -> None:
    assert clean_sbd("12345.0") == "12345"
    assert clean_sbd(12345.0) == "12345"


def test_clean_sbd_handles_none_and_whitespace() -> None:
    assert clean_sbd(None) == ""
    assert clean_sbd("  abc  ") == "abc"


# ── validate_sbd ────────────────────────────────────────────────────


def test_validate_sbd_accepts_alphanumeric() -> None:
    assert validate_sbd("abc-123_xyz") == "abc-123_xyz"


def test_validate_sbd_rejects_path_separators() -> None:
    with pytest.raises(SecurityError, match="invalid characters"):
        validate_sbd("abc/../../etc")


def test_validate_sbd_rejects_empty() -> None:
    with pytest.raises(SecurityError, match="required"):
        validate_sbd("")


def test_validate_sbd_rejects_too_long() -> None:
    with pytest.raises(SecurityError, match="invalid characters"):
        validate_sbd("a" * 65)


# ── validate_request_size ───────────────────────────────────────────


def test_validate_request_size_default_cap() -> None:
    validate_request_size(b"x" * 1024)  # fine


def test_validate_request_size_over_default_cap_raises() -> None:
    with pytest.raises(SecurityError, match="too large"):
        validate_request_size(b"x" * (MAX_REQUEST_BYTES_DEFAULT + 1))


# ── sanitize_filename ───────────────────────────────────────────────


def test_sanitize_filename_strips_unsafe_chars() -> None:
    assert sanitize_filename("my/cert*.pdf") == "my_cert_.pdf"


def test_sanitize_filename_rejects_null_byte() -> None:
    assert "\x00" not in sanitize_filename("a\x00b.pdf")


def test_sanitize_filename_collapses_whitespace() -> None:
    assert sanitize_filename("a    b.pdf") == "a b.pdf"


def test_sanitize_filename_falls_back_to_default() -> None:
    assert sanitize_filename("") == "certificate.pdf"
    assert sanitize_filename("...") == "certificate.pdf"


# ── get_allowed_origins ─────────────────────────────────────────────


def test_default_allowed_origins_wildcard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    assert get_allowed_origins() == DEFAULT_ALLOWED_ORIGINS


def test_allowed_origins_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.example, https://b.example")
    assert get_allowed_origins() == ("https://a.example", "https://b.example")
