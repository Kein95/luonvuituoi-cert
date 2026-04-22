"""Tests for :mod:`luonvuitoi_cert.auth.passwords`."""

from __future__ import annotations

import pytest
from luonvuitoi_cert.auth.passwords import hash_password, verify_password


def test_hash_verify_roundtrip() -> None:
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong password", h)


def test_hash_differs_across_calls() -> None:
    """Salts are random — same password hashes to distinct strings."""
    assert hash_password("pw") != hash_password("pw")


def test_empty_password_refused() -> None:
    with pytest.raises(ValueError):
        hash_password("")


def test_verify_empty_password_returns_false() -> None:
    assert not verify_password("", hash_password("pw"))


def test_verify_malformed_hash_returns_false() -> None:
    assert not verify_password("pw", "not even close")
    assert not verify_password("pw", "pbkdf2$abc$def")  # wrong part count
    assert not verify_password("pw", "unknown$1$a$b")  # wrong algo


def test_verify_empty_stored_hash_returns_false() -> None:
    assert not verify_password("pw", "")


def test_iterations_round_trip() -> None:
    h = hash_password("pw", iterations=1000)
    assert "$1000$" in h
    assert verify_password("pw", h)
