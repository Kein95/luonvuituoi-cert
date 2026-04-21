"""Tests for :mod:`luonvuitoi_cert.api.rate_limiter`."""

from __future__ import annotations

import pytest

from luonvuitoi_cert.api.rate_limiter import RateLimitError, check_rate_limit


class _Clock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_allows_calls_below_limit(kv_memory) -> None:  # type: ignore[no-untyped-def]
    clock = _Clock()
    for i in range(5):
        status = check_rate_limit(kv_memory, "x", "ip-1", limit=5, window_seconds=60, clock=clock)
        assert status.allowed
        assert status.remaining == 4 - i


def test_blocks_beyond_limit(kv_memory) -> None:  # type: ignore[no-untyped-def]
    clock = _Clock()
    for _ in range(3):
        check_rate_limit(kv_memory, "x", "ip-1", limit=3, window_seconds=60, clock=clock)
    with pytest.raises(RateLimitError) as excinfo:
        check_rate_limit(kv_memory, "x", "ip-1", limit=3, window_seconds=60, clock=clock)
    assert excinfo.value.retry_after_seconds >= 1


def test_isolates_by_scope(kv_memory) -> None:  # type: ignore[no-untyped-def]
    clock = _Clock()
    for _ in range(3):
        check_rate_limit(kv_memory, "search", "ip-1", limit=3, window_seconds=60, clock=clock)
    # A different scope keeps its own counter.
    check_rate_limit(kv_memory, "download", "ip-1", limit=3, window_seconds=60, clock=clock)


def test_isolates_by_identifier(kv_memory) -> None:  # type: ignore[no-untyped-def]
    clock = _Clock()
    for _ in range(3):
        check_rate_limit(kv_memory, "search", "ip-1", limit=3, window_seconds=60, clock=clock)
    # Different IP still gets its full quota.
    check_rate_limit(kv_memory, "search", "ip-2", limit=3, window_seconds=60, clock=clock)


def test_resets_after_window(kv_memory) -> None:  # type: ignore[no-untyped-def]
    clock = _Clock()
    for _ in range(3):
        check_rate_limit(kv_memory, "x", "ip-1", limit=3, window_seconds=60, clock=clock)
    with pytest.raises(RateLimitError):
        check_rate_limit(kv_memory, "x", "ip-1", limit=3, window_seconds=60, clock=clock)
    clock.advance(61)
    check_rate_limit(kv_memory, "x", "ip-1", limit=3, window_seconds=60, clock=clock)


def test_invalid_limit_raises(kv_memory) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        check_rate_limit(kv_memory, "x", "ip-1", limit=0, window_seconds=60)
    with pytest.raises(ValueError):
        check_rate_limit(kv_memory, "x", "ip-1", limit=5, window_seconds=0)


def test_corrupt_counter_recovers(kv_memory) -> None:  # type: ignore[no-untyped-def]
    """If the stored counter is garbage, treat as zero and keep going."""
    clock = _Clock()
    # Simulate corruption: set key to non-numeric.
    check_rate_limit(kv_memory, "x", "ip-1", limit=3, window_seconds=60, clock=clock)
    now = int(clock())
    window_start = now - (now % 60)
    kv_memory.set(f"rl:x:ip-1:{window_start}", "not a number", ttl_seconds=120)
    status = check_rate_limit(kv_memory, "x", "ip-1", limit=3, window_seconds=60, clock=clock)
    assert status.allowed
