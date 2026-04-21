"""Single-file JSON key/value store for local development.

Atomic writes via temp-file + ``os.replace``. A process-local
``threading.Lock`` serializes operations so concurrent requests in the dev
server don't clobber each other. Cross-process safety is *not* promised — if
you need that, switch to :class:`RestKV` against Upstash.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path

from luonvuitoi_cert.storage.kv.base import KVError


class LocalFileKV:
    """JSON-backed KV. Durable across process restarts in a single OS user."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path).expanduser().resolve()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ── IO helpers ─────────────────────────────────────────────────
    def _load(self) -> dict[str, tuple[str, float | None]]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise KVError(f"LocalFileKV file is corrupt ({self._path}): {e.msg}") from e
        if not isinstance(raw, dict):
            raise KVError(f"LocalFileKV root must be an object, got {type(raw).__name__}")
        return {k: tuple(v) for k, v in raw.items() if isinstance(v, list) and len(v) == 2}

    def _save(self, data: dict[str, tuple[str, float | None]]) -> None:
        fd, tmp = tempfile.mkstemp(prefix=".kv-", dir=str(self._path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({k: list(v) for k, v in data.items()}, f, ensure_ascii=False)
            os.replace(tmp, self._path)
        except Exception:
            Path(tmp).unlink(missing_ok=True)
            raise

    @staticmethod
    def _is_alive(expires_at: float | None) -> bool:
        return expires_at is None or time.time() < expires_at

    # ── KVBackend surface ──────────────────────────────────────────
    def get(self, key: str) -> str | None:
        with self._lock:
            data = self._load()
            entry = data.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if not self._is_alive(expires_at):
                data.pop(key, None)
                self._save(data)
                return None
            return value

    def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        expires_at = time.time() + ttl_seconds if ttl_seconds and ttl_seconds > 0 else None
        with self._lock:
            data = self._load()
            data[key] = (value, expires_at)
            self._save(data)

    def delete(self, key: str) -> None:
        with self._lock:
            data = self._load()
            if key in data:
                data.pop(key)
                self._save(data)

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def scan_prefix(self, prefix: str, *, limit: int = 100) -> list[str]:
        with self._lock:
            data = self._load()
            alive: list[str] = []
            mutated = False
            for k, (_, expires_at) in list(data.items()):
                if not k.startswith(prefix):
                    continue
                if not self._is_alive(expires_at):
                    data.pop(k, None)
                    mutated = True
                    continue
                alive.append(k)
                if len(alive) >= limit:
                    break
            if mutated:
                self._save(data)
            return alive

    def consume(self, key: str) -> str | None:
        with self._lock:
            data = self._load()
            entry = data.pop(key, None)
            if entry is None:
                return None
            value, expires_at = entry
            # Even on expiry we still write back the pop — frees the slot.
            self._save(data)
            return value if self._is_alive(expires_at) else None
