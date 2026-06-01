"""Fixed-window rate limiter backed by the KV store.

Simpler than a sliding-window log; accepts the well-known burst-at-boundary
trade-off. If a project needs sub-minute precision, swap in a new
:func:`check_rate_limit` implementation — the call signature is the contract,
not the algorithm.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from luonvuitoi_cert.storage.kv.base import KVBackend

KV_PREFIX = "rl:"


class RateLimitError(Exception):
    """Raised when a caller exceeds their quota for the current window."""

    def __init__(self, message: str, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True, slots=True)
class RateLimitStatus:
    allowed: bool
    remaining: int
    retry_after_seconds: int


def check_rate_limit(
    kv: KVBackend,
    scope: str,
    identifier: str,
    *,
    limit: int,
    window_seconds: int = 60,
    clock: Callable[[], float] | None = None,
) -> RateLimitStatus:
    """Record a request and raise :class:`RateLimitError` if it exceeds ``limit``.

    ``scope`` namespaces the counter (e.g. ``"search"``, ``"download"``);
    ``identifier`` is typically the client IP or admin user. Use distinct
    scopes when different endpoints should have different quotas.
    """
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if window_seconds < 1:
        raise ValueError("window_seconds must be >= 1")

    now = int((clock or time.time)())
    window_start = now - (now % window_seconds)
    key = f"{KV_PREFIX}{scope}:{identifier}:{window_start}"

    # Atomic increment-and-count: a single op closes the read-modify-write race
    # where concurrent requests all read the same count before any write and
    # slip past the cap. The window key carries a TTL so it self-expires.
    count = kv.incr(key, ttl_seconds=window_seconds * 2)

    elapsed = now - window_start
    retry_after = max(window_seconds - elapsed, 1)

    if count > limit:
        raise RateLimitError(
            f"rate limit exceeded for {scope!r} (identifier={identifier!r}); retry in {retry_after}s",
            retry_after_seconds=retry_after,
        )
    return RateLimitStatus(allowed=True, remaining=max(limit - count, 0), retry_after_seconds=retry_after)
