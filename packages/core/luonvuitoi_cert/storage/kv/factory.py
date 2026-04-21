"""Factory that picks a KV backend based on config + env.

Kept separate from the adapters so the ``from luonvuitoi_cert.storage.kv
import open_kv`` import path doesn't drag httpx into test environments that
only need the in-memory store.
"""

from __future__ import annotations

import os
from pathlib import Path

from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.storage.kv.base import KVBackend, KVError
from luonvuitoi_cert.storage.kv.local import LocalFileKV
from luonvuitoi_cert.storage.kv.rest import RestKV


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
        return LocalFileKV(path)

    if choice == "upstash":
        return RestKV.from_upstash_env(env)

    if choice == "vercel-kv":
        return RestKV.from_vercel_env(env)

    raise KVError(f"unsupported kv_backend: {choice!r}")
