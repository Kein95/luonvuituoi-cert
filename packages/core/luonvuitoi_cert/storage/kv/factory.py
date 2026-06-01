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
    """Return a :class:`KVBackend` selecting the backend from env or config.

    The ``KV_BACKEND`` env var takes precedence over
    ``config.features.kv_backend`` so the knob advertised in ``.env`` /
    ``docker-compose`` actually controls the backend. Accepted values:

    - ``local`` → :class:`LocalFileKV` at ``project_root/.kv/store.json`` (or
      ``$KV_LOCAL_PATH`` if set).
    - ``upstash`` → :class:`RestKV` from ``UPSTASH_REDIS_REST_URL`` /
      ``UPSTASH_REDIS_REST_TOKEN``.
    - ``vercel-kv`` → :class:`RestKV` from ``KV_REST_API_URL`` /
      ``KV_REST_API_TOKEN``.
    """
    env = env if env is not None else dict(os.environ)
    # Env wins over config so the documented KV_BACKEND knob isn't inert.
    choice = (env.get("KV_BACKEND") or "").strip() or config.features.kv_backend

    if choice == "local":
        override = env.get("KV_LOCAL_PATH")
        path = Path(override) if override else Path(project_root) / ".kv" / "store.json"
        # LocalFileKV serializes with a per-process threading.Lock — safe within
        # one process but NOT cross-process. Multiple workers race the
        # read-modify-write and can replay single-use CAPTCHA/OTP/magic-link
        # tokens or undercount rate limits, so refuse to run rather than warn.
        workers = _detect_worker_count(env)
        if workers is not None and workers > 1:
            raise KVError(
                f"kv_backend 'local' is unsafe with {workers} workers — concurrent "
                "processes race single-use tokens and rate-limit counters. Set "
                "KV_BACKEND=upstash or vercel-kv, or run a single worker."
            )
        return LocalFileKV(path)

    if choice == "upstash":
        return RestKV.from_upstash_env(env)

    if choice == "vercel-kv":
        return RestKV.from_vercel_env(env)

    raise KVError(f"unsupported kv_backend: {choice!r}")
