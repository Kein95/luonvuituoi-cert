"""Key/value backends for transient portal state.

Three backends ship:
- :class:`LocalFileKV` — JSON file, ideal for ``lvt-cert dev`` and tests
- :class:`RestKV` — REST Redis protocol, speaks Upstash and Vercel KV
- stub (no-op) when an empty/invalid configuration is passed; handlers that
  truly need KV will surface a clear error at use time

Pick one with :func:`open_kv` — it reads ``config.features.kv_backend`` and
the environment for credentials.
"""

from luonvuitoi_cert.storage.kv.base import KVBackend, KVError, MemoryKV
from luonvuitoi_cert.storage.kv.factory import open_kv
from luonvuitoi_cert.storage.kv.local import LocalFileKV
from luonvuitoi_cert.storage.kv.rest import RestKV

__all__ = [
    "KVBackend",
    "KVError",
    "LocalFileKV",
    "MemoryKV",
    "RestKV",
    "open_kv",
]
