"""KV backend contract + in-memory implementation for tests.

The interface stays minimal on purpose: ``get``, ``set`` (with optional TTL),
``delete``, ``exists``, and a bulk ``scan_prefix``. Everything else (hashes,
sorted sets, transactions) is intentionally out of scope — if a handler
decides it needs richer semantics, it can pick a vendor-specific client
directly. Staying on the narrow subset keeps backend swaps painless.
"""

from __future__ import annotations

import threading
import time
from typing import Protocol, runtime_checkable


class KVError(Exception):
    """Raised when a KV operation fails due to transport / auth / quota issues."""


@runtime_checkable
class KVBackend(Protocol):
    """Common surface every KV adapter must expose."""

    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def scan_prefix(self, prefix: str, *, limit: int = 100) -> list[str]: ...


class MemoryKV:
    """In-process ``dict`` backend. Used by tests + embedded scenarios.

    Not durable, not multi-process — don't rely on it in production handlers
    even if the import is convenient.
    """

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float | None]] = {}
        self._lock = threading.Lock()

    def _is_alive(self, expires_at: float | None) -> bool:
        return expires_at is None or time.time() < expires_at

    def get(self, key: str) -> str | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if not self._is_alive(expires_at):
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        expires_at = time.time() + ttl_seconds if ttl_seconds and ttl_seconds > 0 else None
        with self._lock:
            self._data[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def scan_prefix(self, prefix: str, *, limit: int = 100) -> list[str]:
        with self._lock:
            alive: list[str] = []
            for k, (_, expires_at) in list(self._data.items()):
                if not k.startswith(prefix):
                    continue
                if not self._is_alive(expires_at):
                    self._data.pop(k, None)
                    continue
                alive.append(k)
                if len(alive) >= limit:
                    break
            return alive
