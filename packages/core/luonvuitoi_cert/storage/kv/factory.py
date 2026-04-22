"""Factory that picks a KV backend based on config + env.

Kept separate from the adapters so the ``from luonvuitoi_cert.storage.kv
import open_kv`` import path doesn't drag httpx into test environments that
only need the in-memory store.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.storage.kv.base import KVBackend, KVError
from luonvuitoi_cert.storage.kv.local import LocalFileKV
from luonvuitoi_cert.storage.kv.rest import RestKV

_LOGGER = logging.getLogger(__name__)


def _detect_worker_count(env: dict[str, str]) -> int | None:
    """Parse the worker count from common hosts (gunicorn, uvicorn, waitress).

    Returns ``None`` when we can't tell — single-process local dev with Flask
    doesn't set these and shouldn't trigger the warning.
    """
    for key in ("WEB_CONCURRENCY", "GUNICORN_WORKERS", "UVICORN_WORKERS"):
        raw = env.get(key, "").strip()
        if raw.isdigit() and int(raw) >= 1:
            return int(raw)
    return None


def open_kv(
    config: CertConfig,
    project_root: str | Path,
    env: dict[str, str] | None = None,
) -> KVBackend:
    """Return a :class:`KVBackend` matching ``config.features.kv_backend``.

    - ``local`` → :class:`LocalFileKV` at ``project_root/.kv/store.json`` (or
      ``$KV_LOCAL_PATH`` if set).
    - ``upstash`` → :class:`RestKV` from ``UPSTASH_REDIS_REST_URL`` /
      ``UPSTASH_REDIS_REST_TOKEN``.
    - ``vercel-kv`` → :class:`RestKV` from ``KV_REST_API_URL`` /
      ``KV_REST_API_TOKEN``.
    """
    env = env if env is not None else dict(os.environ)
    choice = config.features.kv_backend

    if choice == "local":
        override = env.get("KV_LOCAL_PATH")
        path = Path(override) if override else Path(project_root) / ".kv" / "store.json"
        # H2: LocalFileKV uses a threading.Lock — safe within one process but
        # NOT cross-process. Gunicorn/uvicorn running >1 worker can race on the
        # read-modify-write cycle and lose CAPTCHA / rate-limit / OTP entries.
        workers = _detect_worker_count(env)
        if workers is not None and workers > 1:
            _LOGGER.warning(
                "KV_BACKEND=local with %d workers is unsafe — concurrent reads can "
                "lose writes. Use KV_BACKEND=upstash or vercel-kv in production.",
                workers,
            )
        return LocalFileKV(path)

    if choice == "upstash":
        return RestKV.from_upstash_env(env)

    if choice == "vercel-kv":
        return RestKV.from_vercel_env(env)

    raise KVError(f"unsupported kv_backend: {choice!r}")
