"""Tests for :mod:`luonvuitoi_cert.shipment` (schema + repository)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.shipment import (
    ShipmentError,
    build_shipment_schema,
    ensure_shipment_schema,
    get_shipment,
    list_shipments,
    upsert_shipment,
)
from luonvuitoi_cert.shipment.schema import ShipmentSchemaError


def _cfg(**overrides) -> CertConfig:  # type: ignore[no-untyped-def]
    raw = {
        "project": {"name": "T", "slug": "t"},
        "rounds": [{"id": "main", "label": "Main", "table": "students", "pdf": "t.pdf"}],
        "subjects": [{"code": "S", "en": "S", "db_col": "s"}],
        "results": {"S": {"GOLD": 1}},
        "layout": {
            "page_size": [100, 100],
            "fields": {"n": {"x": 0, "y": 0, "font": "f", "size": 10, "align": "left"}},
        },
        "fonts": {"f": "f.ttf"},
        "features": {
            "shipment": {
                "enabled": True,
                "statuses": ["pending", "shipped", "delivered"],
                "fields": ["tracking_code", "carrier"],
            }
        },
    }
    raw.update(overrides)
    return CertConfig.model_validate(raw)


# ── schema ─────────────────────────────────────────────────────────


def test_schema_disabled_raises() -> None:
    cfg = _cfg(features={"shipment": {"enabled": False}})
    with pytest.raises(ShipmentSchemaError):
        build_shipment_schema(cfg)


def test_schema_contains_fixed_and_extra_columns() -> None:
    sql = build_shipment_schema(_cfg())
    for col in ("id", "round_id", "sbd", "status", "created_at", "updated_at"):
        assert f'"{col}"' in sql
    assert '"tracking_code"' in sql
    assert '"carrier"' in sql
    assert 'UNIQUE("round_id", "sbd")' in sql


def test_ensure_schema_creates_table(tmp_path: Path) -> None:
    db = tmp_path / "ship.db"
    ensure_shipment_schema(db, _cfg())
    conn = sqlite3.connect(str(db))
    rows = conn.execute("PRAGMA table_info(shipments)").fetchall()
    conn.close()
    names = [r[1] for r in rows]
    assert "tracking_code" in names and "status" in names


# ── config validation ──────────────────────────────────────────────


def test_config_rejects_reserved_field_name() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="reserved"):
        CertConfig.model_validate(
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
                "features": {"shipment": {"fields": ["status"]}},  # reserved
            }
        )


def test_config_rejects_duplicate_field_names() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="unique"):
        CertConfig.model_validate(
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
                "features": {"shipment": {"fields": ["a", "a"]}},
            }
        )


def test_config_rejects_sql_injection_in_field() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="SQL identifier"):
        CertConfig.model_validate(
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
                "features": {"shipment": {"fields": ["x; DROP TABLE shipments"]}},
            }
        )


# ── repository ─────────────────────────────────────────────────────


def test_upsert_creates_new_record(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "ship.db"
    rec = upsert_shipment(
        db,
        cfg,
        round_id="main",
        sbd="12345",
        status="shipped",
        fields={"tracking_code": "VN123", "carrier": "GHN"},
    )
    assert rec.status == "shipped"
    assert rec.fields["tracking_code"] == "VN123"
    assert rec.created_at == rec.updated_at  # fresh insert


def test_upsert_updates_existing_record(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "ship.db"
    upsert_shipment(db, cfg, round_id="main", sbd="12345", status="pending", fields={"tracking_code": "A"})
    rec = upsert_shipment(db, cfg, round_id="main", sbd="12345", status="delivered", fields={"carrier": "GHN"})
    assert rec.status == "delivered"
    assert rec.fields["tracking_code"] == "A"  # previous value preserved
    assert rec.fields["carrier"] == "GHN"


def test_upsert_rejects_unknown_status(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "ship.db"
    with pytest.raises(ShipmentError, match="not in"):
        upsert_shipment(db, cfg, round_id="main", sbd="1", status="lost")


def test_upsert_rejects_unknown_field(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "ship.db"
    with pytest.raises(ShipmentError, match="unknown shipment fields"):
        upsert_shipment(db, cfg, round_id="main", sbd="1", status="pending", fields={"totally_fake": "x"})


def test_get_shipment_returns_none_for_missing(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "ship.db"
    assert get_shipment(db, cfg, round_id="main", sbd="ghost") is None


def test_list_shipments_filters_and_sorts(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "ship.db"
    upsert_shipment(db, cfg, round_id="main", sbd="1", status="pending")
    upsert_shipment(db, cfg, round_id="main", sbd="2", status="shipped")
    upsert_shipment(db, cfg, round_id="main", sbd="3", status="shipped")
    all_rows = list_shipments(db, cfg)
    assert len(all_rows) == 3
    shipped_only = list_shipments(db, cfg, status="shipped")
    assert len(shipped_only) == 2
    assert {r.sbd for r in shipped_only} == {"2", "3"}
