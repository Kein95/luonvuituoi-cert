"""Persistence layer: SQLite schema derivation and key/value adapters.

SQLite holds the authoritative student table(s) — one per round. Transient
state (rate-limit counters, per-student admin overrides, OTP challenges) lives
in a KV backend (local file for dev, Upstash/Vercel KV for serverless).
"""

from luonvuitoi_cert.storage.kv import KVBackend, LocalFileKV, RestKV, open_kv
from luonvuitoi_cert.storage.sqlite_schema import (
    ColumnSpec,
    SchemaError,
    TableSpec,
    build_schema,
    render_create_sql,
)

__all__ = [
    "ColumnSpec",
    "KVBackend",
    "LocalFileKV",
    "RestKV",
    "SchemaError",
    "TableSpec",
    "build_schema",
    "open_kv",
    "render_create_sql",
]
