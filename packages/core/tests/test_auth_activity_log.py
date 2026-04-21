"""Tests for :mod:`luonvuitoi_cert.auth.activity_log`."""

from __future__ import annotations

from pathlib import Path

from luonvuitoi_cert.auth.activity_log import ActivityLog, log_admin_action, resolve_webhook_url


def test_log_and_recent_roundtrip(tmp_path: Path) -> None:
    log = ActivityLog(tmp_path / "db.sqlite")
    log_admin_action(log, user_id="u1", user_email="a@b.co", action="student.update", target_id="s:1", metadata={"k": "v"})
    log_admin_action(log, user_id="u1", user_email="a@b.co", action="login", target_id=None)
    entries = log.recent(limit=10)
    assert len(entries) == 2
    assert entries[0].action == "login"  # recent-first ordering
    assert entries[1].metadata == {"k": "v"}


def test_webhook_failure_does_not_break_logging(tmp_path: Path) -> None:
    log = ActivityLog(tmp_path / "db.sqlite", gsheet_webhook_url="http://127.0.0.1:1/unreachable")
    # Should log locally even if the webhook can't be reached.
    log_admin_action(log, user_id=None, user_email=None, action="noop", target_id=None)
    assert len(log.recent()) == 1


def test_metadata_can_hold_unicode(tmp_path: Path) -> None:
    log = ActivityLog(tmp_path / "db.sqlite")
    log_admin_action(log, user_id="u", user_email="e@x.co", action="a", metadata={"note": "Chào bạn"})
    assert log.recent()[0].metadata["note"] == "Chào bạn"


def test_resolve_webhook_url_env_empty() -> None:
    assert resolve_webhook_url({}) is None
    assert resolve_webhook_url({"GSHEET_WEBHOOK_URL": "   "}) is None
    assert resolve_webhook_url({"GSHEET_WEBHOOK_URL": "https://hook"}) == "https://hook"
