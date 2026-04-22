"""Audit trail for admin actions.

Entries land in a ``admin_activity`` SQLite table. If a Google Sheets webhook
URL is configured (``GSHEET_WEBHOOK_URL`` env), a copy is POSTed fire-and-
forget — the local log is always authoritative; webhook failures never break
the admin flow.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import sqlite3
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

import httpx

_LOGGER = logging.getLogger(__name__)

# H4: a single bounded executor per process, not one thread per admin action.
# Uploading a 10k-row CSV triggers 10k audit writes — without this cap we'd
# spawn 10k daemon threads and the interpreter would thrash the scheduler.
_WEBHOOK_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="activity-log-webhook")
atexit.register(_WEBHOOK_EXECUTOR.shutdown, wait=False)

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS admin_activity (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    user_id TEXT,
    user_email TEXT,
    action TEXT NOT NULL,
    target_id TEXT,
    metadata TEXT,
    ip TEXT
);
"""


@dataclass(frozen=True, slots=True)
class ActivityLogEntry:
    id: str
    timestamp: str
    user_id: str | None
    user_email: str | None
    action: str
    target_id: str | None
    metadata: dict[str, object] = field(default_factory=dict)
    ip: str | None = None


def _validated_webhook_url(url: str | None) -> str | None:
    """Accept https:// only; drop everything else with a warning."""
    if not url:
        return None
    if not url.strip().lower().startswith("https://"):
        _LOGGER.warning(
            "activity log webhook must be https://; got scheme prefix %r — disabled.",
            url[:20],
        )
        return None
    return url.strip()


class ActivityLog:
    """Helper wrapper over the SQLite audit table. Instantiate once per DB path."""

    def __init__(self, db_path: str | Path, *, gsheet_webhook_url: str | None = None) -> None:
        self._db_path = Path(db_path).expanduser().resolve()
        # M6: filter the URL through the same validator that resolve_webhook_url
        # applies so direct instantiation (e.g. tests, CLI, Vercel shim) gets
        # the same SSRF guard.
        self._webhook = _validated_webhook_url(gsheet_webhook_url)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(str(self._db_path))) as conn, conn:
            conn.execute(_CREATE_SQL)

    def log(self, entry: ActivityLogEntry) -> None:
        with closing(sqlite3.connect(str(self._db_path))) as conn, conn:
            conn.execute(
                "INSERT INTO admin_activity "
                "(id, timestamp, user_id, user_email, action, target_id, metadata, ip) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.id,
                    entry.timestamp,
                    entry.user_id,
                    entry.user_email,
                    entry.action,
                    entry.target_id,
                    json.dumps(entry.metadata, ensure_ascii=False),
                    entry.ip,
                ),
            )
        self._forward_to_webhook(entry)

    def recent(self, *, limit: int = 100) -> list[ActivityLogEntry]:
        with closing(sqlite3.connect(str(self._db_path))) as conn:
            conn.row_factory = sqlite3.Row
            # ``rowid DESC`` breaks timestamp ties (insertions in the same second).
            rows = conn.execute(
                "SELECT * FROM admin_activity ORDER BY timestamp DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            ActivityLogEntry(
                id=r["id"],
                timestamp=r["timestamp"],
                user_id=r["user_id"],
                user_email=r["user_email"],
                action=r["action"],
                target_id=r["target_id"],
                metadata=json.loads(r["metadata"] or "{}"),
                ip=r["ip"],
            )
            for r in rows
        ]

    def _forward_to_webhook(self, entry: ActivityLogEntry) -> None:
        """Fire-and-forget: spawn a daemon thread so admin actions don't wait on I/O.

        The local SQLite write has already happened synchronously, so even if
        the thread is killed by interpreter shutdown the audit record is safe.
        """
        if not self._webhook:
            return
        payload = {
            "id": entry.id,
            "timestamp": entry.timestamp,
            "user_id": entry.user_id,
            "user_email": entry.user_email,
            "action": entry.action,
            "target_id": entry.target_id,
            "metadata": entry.metadata,
            "ip": entry.ip,
        }
        try:
            _WEBHOOK_EXECUTOR.submit(self._post_webhook, payload)
        except RuntimeError:
            # Interpreter already shutting down; local SQLite record is
            # authoritative — forwarding loss is acceptable.
            _LOGGER.debug("activity log executor shut down; skipping webhook")

    def _post_webhook(self, payload: dict[str, object]) -> None:
        try:
            httpx.post(self._webhook, json=payload, timeout=3.0)  # type: ignore[arg-type]
        except httpx.HTTPError as e:
            _LOGGER.warning("activity log webhook POST failed: %s", e)


def log_admin_action(
    log: ActivityLog,
    *,
    user_id: str | None,
    user_email: str | None,
    action: str,
    target_id: str | None = None,
    metadata: dict[str, object] | None = None,
    ip: str | None = None,
) -> ActivityLogEntry:
    """Convenience builder — timestamps the entry and hands it to :class:`ActivityLog`."""
    entry = ActivityLogEntry(
        id=str(uuid.uuid4()),
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        user_id=user_id,
        user_email=user_email,
        action=action,
        target_id=target_id,
        metadata=metadata or {},
        ip=ip,
    )
    log.log(entry)
    return entry


def resolve_webhook_url(env: dict[str, str] | None = None) -> str | None:
    """Return the configured webhook URL if it's an ``https://`` target, else ``None``.

    M6: env-provided URL previously accepted any scheme — including ``http://``
    internal hosts or ``file://`` paths, giving a would-be attacker an SSRF
    vector if they could set the env var. We require explicit ``https://`` and
    log-then-drop anything else so operators notice misconfig.
    """
    source = env if env is not None else os.environ
    url = source.get("GSHEET_WEBHOOK_URL", "").strip()
    if not url:
        return None
    if not url.lower().startswith("https://"):
        _LOGGER.warning(
            "GSHEET_WEBHOOK_URL must be https:// (got scheme from %r); webhook disabled.",
            url[:20],
        )
        return None
    return url
