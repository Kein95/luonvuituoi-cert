"""Tests for :mod:`luonvuitoi_cert.api.shipment` (admin upsert + public lookup)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from luonvuitoi_cert.api.captcha import issue_challenge
from luonvuitoi_cert.api.rate_limiter import RateLimitError
from luonvuitoi_cert.api.security import SecurityError
from luonvuitoi_cert.api.shipment import (
    ShipmentHandlerError,
    lookup_shipment,
    upsert_shipment_record,
)
from luonvuitoi_cert.auth import ActivityLog, Role, issue_admin_token
from luonvuitoi_cert.config import CertConfig


def _env() -> dict[str, str]:
    return {"JWT_SECRET": "pytest-default-secret-padded-32-bytes-min"}


def _cfg(enabled: bool = True, public_fields: list[str] | None = None) -> CertConfig:
    shipment_cfg: dict = {
        "enabled": enabled,
        "statuses": ["pending", "shipped", "delivered"],
        "fields": ["tracking_code", "carrier"],
    }
    if public_fields is not None:
        shipment_cfg["public_fields"] = public_fields
    return CertConfig.model_validate(
        {
            "project": {"name": "T", "slug": "t"},
            "rounds": [{"id": "main", "label": "Main", "table": "students", "pdf": "t.pdf"}],
            "subjects": [{"code": "S", "en": "S", "db_col": "s"}],
            "results": {"S": {"GOLD": 1}},
            "layout": {
                "page_size": [100, 100],
                "fields": {"n": {"x": 0, "y": 0, "font": "f", "size": 10, "align": "left"}},
            },
            "fonts": {"f": "f.ttf"},
            "features": {"shipment": shipment_cfg},
        }
    )


def _solve(question: str) -> int:
    a, op, b = re.match(r"(\d+)\s*([+\-×])\s*(\d+)", question).groups()  # type: ignore[union-attr]
    return {"+": int(a) + int(b), "-": int(a) - int(b), "×": int(a) * int(b)}[op]


def _lookup_params(kv, **extra) -> dict:  # type: ignore[no-untyped-def]
    ch = issue_challenge(kv)
    return {
        "sbd": "12345",
        "round_id": "main",
        "captcha_id": ch.id,
        "captcha_answer": _solve(ch.question),
        **extra,
    }


# ── Admin upsert ────────────────────────────────────────────────────


def test_admin_creates_shipment(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "s.db"
    audit = ActivityLog(tmp_path / "a.db")
    token = issue_admin_token(user_id="u1", email="a@b.co", role=Role.ADMIN, env=_env())
    rec = upsert_shipment_record(
        config=cfg,
        db_path=db,
        activity=audit,
        params={
            "token": token,
            "sbd": "12345",
            "round_id": "main",
            "status": "shipped",
            "updates": {"tracking_code": "VN1"},
        },
        env=_env(),
    )
    assert rec.status == "shipped"
    assert audit.recent()[0].action == "shipment.upsert"


def test_admin_viewer_role_rejected(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "s.db"
    audit = ActivityLog(tmp_path / "a.db")
    token = issue_admin_token(user_id="u1", email="a@b.co", role=Role.VIEWER, env=_env())
    with pytest.raises(ShipmentHandlerError, match="viewer"):
        upsert_shipment_record(
            config=cfg,
            db_path=db,
            activity=audit,
            params={"token": token, "sbd": "1", "round_id": "main", "status": "shipped"},
            env=_env(),
        )


def test_audit_log_redacts_field_values(tmp_path: Path) -> None:
    """Regression: Phase 09 review M1 — audit must not echo raw field values into the webhook stream."""
    cfg = _cfg()
    db = tmp_path / "s.db"
    audit = ActivityLog(tmp_path / "a.db")
    token = issue_admin_token(user_id="u1", email="a@b.co", role=Role.ADMIN, env=_env())
    upsert_shipment_record(
        config=cfg,
        db_path=db,
        activity=audit,
        params={
            "token": token,
            "sbd": "12345",
            "round_id": "main",
            "status": "shipped",
            "updates": {"tracking_code": "SECRET-TRACKING-123"},
        },
        env=_env(),
    )
    entry = audit.recent()[0]
    assert "SECRET-TRACKING-123" not in str(entry.metadata)
    assert entry.metadata["fields_touched"] == ["tracking_code"]


def test_admin_rejects_unknown_round(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "s.db"
    audit = ActivityLog(tmp_path / "a.db")
    token = issue_admin_token(user_id="u1", email="a@b.co", role=Role.ADMIN, env=_env())
    with pytest.raises(ShipmentHandlerError, match="unknown round_id"):
        upsert_shipment_record(
            config=cfg,
            db_path=db,
            activity=audit,
            params={"token": token, "sbd": "1", "round_id": "ghost", "status": "shipped"},
            env=_env(),
        )


def test_admin_rejects_invalid_status(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "s.db"
    audit = ActivityLog(tmp_path / "a.db")
    token = issue_admin_token(user_id="u1", email="a@b.co", role=Role.ADMIN, env=_env())
    with pytest.raises(ShipmentHandlerError, match="not in"):
        upsert_shipment_record(
            config=cfg,
            db_path=db,
            activity=audit,
            params={"token": token, "sbd": "1", "round_id": "main", "status": "lost"},
            env=_env(),
        )


def test_admin_rejects_non_dict_updates(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "s.db"
    audit = ActivityLog(tmp_path / "a.db")
    token = issue_admin_token(user_id="u1", email="a@b.co", role=Role.ADMIN, env=_env())
    with pytest.raises(SecurityError):
        upsert_shipment_record(
            config=cfg,
            db_path=db,
            activity=audit,
            params={
                "token": token,
                "sbd": "1",
                "round_id": "main",
                "status": "shipped",
                "updates": "not-a-dict",
            },
            env=_env(),
        )


def test_admin_disabled_feature(tmp_path: Path) -> None:
    cfg = _cfg(enabled=False)
    db = tmp_path / "s.db"
    audit = ActivityLog(tmp_path / "a.db")
    token = issue_admin_token(user_id="u1", email="a@b.co", role=Role.ADMIN, env=_env())
    with pytest.raises(ShipmentHandlerError, match="disabled"):
        upsert_shipment_record(
            config=cfg,
            db_path=db,
            activity=audit,
            params={"token": token, "sbd": "1", "round_id": "main", "status": "shipped"},
            env=_env(),
        )


# ── Public lookup ───────────────────────────────────────────────────


def test_public_lookup_returns_status(tmp_path: Path, kv_memory) -> None:  # type: ignore[no-untyped-def]
    cfg = _cfg(public_fields=["tracking_code"])
    db = tmp_path / "s.db"
    audit = ActivityLog(tmp_path / "a.db")
    token = issue_admin_token(user_id="u1", email="a@b.co", role=Role.ADMIN, env=_env())
    upsert_shipment_record(
        config=cfg,
        db_path=db,
        activity=audit,
        params={
            "token": token,
            "sbd": "12345",
            "round_id": "main",
            "status": "shipped",
            "updates": {"tracking_code": "VN1", "carrier": "GHN"},
        },
        env=_env(),
    )
    resp = lookup_shipment(
        config=cfg, db_path=db, kv=kv_memory, params=_lookup_params(kv_memory), client_id="ip-1"
    )
    assert resp.status == "shipped"
    assert resp.fields == {"tracking_code": "VN1"}  # carrier NOT in public_fields


def test_public_lookup_defaults_to_no_fields(tmp_path: Path, kv_memory) -> None:  # type: ignore[no-untyped-def]
    """Regression: Phase 09 review H1 — lookup used to return ALL fields."""
    cfg = _cfg()  # no public_fields
    db = tmp_path / "s.db"
    audit = ActivityLog(tmp_path / "a.db")
    token = issue_admin_token(user_id="u1", email="a@b.co", role=Role.ADMIN, env=_env())
    upsert_shipment_record(
        config=cfg,
        db_path=db,
        activity=audit,
        params={
            "token": token,
            "sbd": "12345",
            "round_id": "main",
            "status": "shipped",
            "updates": {"tracking_code": "VN1", "carrier": "GHN"},
        },
        env=_env(),
    )
    resp = lookup_shipment(
        config=cfg, db_path=db, kv=kv_memory, params=_lookup_params(kv_memory), client_id="ip-1"
    )
    assert resp.fields == {}  # default empty allowlist


def test_public_lookup_unknown_student(tmp_path: Path, kv_memory) -> None:  # type: ignore[no-untyped-def]
    cfg = _cfg()
    db = tmp_path / "s.db"
    with pytest.raises(ShipmentHandlerError, match="no shipment"):
        lookup_shipment(
            config=cfg, db_path=db, kv=kv_memory, params=_lookup_params(kv_memory, sbd="99999"), client_id="ip-1"
        )


def test_public_lookup_rate_limits(tmp_path: Path, kv_memory) -> None:  # type: ignore[no-untyped-def]
    cfg = _cfg()
    db = tmp_path / "s.db"
    audit = ActivityLog(tmp_path / "a.db")
    token = issue_admin_token(user_id="u1", email="a@b.co", role=Role.ADMIN, env=_env())
    upsert_shipment_record(
        config=cfg,
        db_path=db,
        activity=audit,
        params={"token": token, "sbd": "12345", "round_id": "main", "status": "shipped"},
        env=_env(),
    )
    for _ in range(20):
        lookup_shipment(
            config=cfg, db_path=db, kv=kv_memory, params=_lookup_params(kv_memory), client_id="ip-1"
        )
    with pytest.raises(RateLimitError):
        lookup_shipment(
            config=cfg, db_path=db, kv=kv_memory, params=_lookup_params(kv_memory), client_id="ip-1"
        )


def test_public_lookup_disabled_feature(tmp_path: Path, kv_memory) -> None:  # type: ignore[no-untyped-def]
    cfg = _cfg(enabled=False)
    db = tmp_path / "s.db"
    with pytest.raises(ShipmentHandlerError, match="disabled"):
        lookup_shipment(
            config=cfg, db_path=db, kv=kv_memory, params=_lookup_params(kv_memory), client_id="ip-1"
        )


def test_lookup_response_omits_internal_id(tmp_path: Path, kv_memory) -> None:  # type: ignore[no-untyped-def]
    """Regression: response shape must not leak the internal UUID row id."""
    cfg = _cfg()
    db = tmp_path / "s.db"
    audit = ActivityLog(tmp_path / "a.db")
    token = issue_admin_token(user_id="u1", email="a@b.co", role=Role.ADMIN, env=_env())
    upsert_shipment_record(
        config=cfg,
        db_path=db,
        activity=audit,
        params={"token": token, "sbd": "12345", "round_id": "main", "status": "shipped"},
        env=_env(),
    )
    resp = lookup_shipment(
        config=cfg, db_path=db, kv=kv_memory, params=_lookup_params(kv_memory), client_id="ip-1"
    )
    assert not hasattr(resp, "id")
    assert not hasattr(resp, "created_at")
