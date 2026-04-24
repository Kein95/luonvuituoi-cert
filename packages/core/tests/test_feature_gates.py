"""Tests for :mod:`luonvuitoi_cert.api.feature_gates` — pure KV semantics."""

from __future__ import annotations

import pytest
from luonvuitoi_cert.api.feature_gates import (
    FeatureDisabledError,
    get_state,
    require_public_download,
    require_public_lookup,
    set_state,
)
from luonvuitoi_cert.storage.kv.base import MemoryKV


def test_defaults_to_both_on_when_kv_empty() -> None:
    state = get_state(MemoryKV())
    assert state.lookup_enabled is True
    assert state.download_enabled is True


def test_set_persists_lookup_on_download_on() -> None:
    kv = MemoryKV()
    state = set_state(kv, lookup_enabled=True, download_enabled=True)
    assert state.lookup_enabled is True
    assert state.download_enabled is True
    assert get_state(kv) == state


def test_set_persists_lookup_on_download_off() -> None:
    kv = MemoryKV()
    state = set_state(kv, lookup_enabled=True, download_enabled=False)
    assert state.lookup_enabled is True
    assert state.download_enabled is False


def test_lookup_off_forces_download_off_on_write() -> None:
    """Invariant: download can't be on when lookup is off (write-side clamp)."""
    kv = MemoryKV()
    state = set_state(kv, lookup_enabled=False, download_enabled=True)
    assert state.lookup_enabled is False
    assert state.download_enabled is False


def test_lookup_off_forces_download_off_on_read() -> None:
    """Invariant also holds at read time even if KV was seeded by hand."""
    kv = MemoryKV()
    # Seed KV with an inconsistent pair (simulates manual intervention).
    kv.set("feature:public_lookup_enabled", "0")
    kv.set("feature:public_download_enabled", "1")
    state = get_state(kv)
    assert state.lookup_enabled is False
    assert state.download_enabled is False


def test_require_lookup_raises_when_off() -> None:
    kv = MemoryKV()
    set_state(kv, lookup_enabled=False, download_enabled=False)
    with pytest.raises(FeatureDisabledError, match="lookup"):
        require_public_lookup(kv)


def test_require_lookup_ok_when_on() -> None:
    kv = MemoryKV()
    set_state(kv, lookup_enabled=True, download_enabled=False)
    require_public_lookup(kv)  # no raise


def test_require_download_raises_when_lookup_off() -> None:
    kv = MemoryKV()
    set_state(kv, lookup_enabled=False, download_enabled=False)
    # Lookup message wins — downstream gate inherits upstream failure.
    with pytest.raises(FeatureDisabledError, match="lookup"):
        require_public_download(kv)


def test_require_download_raises_when_download_off() -> None:
    kv = MemoryKV()
    set_state(kv, lookup_enabled=True, download_enabled=False)
    with pytest.raises(FeatureDisabledError, match="download"):
        require_public_download(kv)


def test_require_download_ok_when_both_on() -> None:
    kv = MemoryKV()
    set_state(kv, lookup_enabled=True, download_enabled=True)
    require_public_download(kv)  # no raise


def test_accepts_truthy_string_variants() -> None:
    kv = MemoryKV()
    for value in ("1", "true", "yes", "on"):
        kv.set("feature:public_lookup_enabled", value)
        kv.set("feature:public_download_enabled", value)
        state = get_state(kv)
        assert state.lookup_enabled is True, value
        assert state.download_enabled is True, value
