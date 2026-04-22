"""Tests for :mod:`luonvuitoi_cert.storage.sqlite_schema`."""

from __future__ import annotations

import sqlite3

import pytest
from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.storage import SchemaError, build_schema, render_create_sql


def _config(**overrides: object) -> CertConfig:
    raw: dict = {
        "project": {"name": "DEMO", "slug": "demo"},
        "rounds": [{"id": "main", "label": "Main", "table": "students", "pdf": "t.pdf"}],
        "subjects": [
            {"code": "S", "en": "Science", "db_col": "science_result"},
            {"code": "E", "en": "English", "db_col": "english_result"},
        ],
        "results": {"S": {"GOLD": 1}, "E": {"GOLD": 2}},
        "data_mapping": {
            "sbd_col": "registration_number",
            "name_col": "full_name",
            "dob_col": "date_of_birth",
            "school_col": "school",
            "extra_cols": ["province"],
        },
        "layout": {
            "page_size": [842, 595],
            "fields": {"name": {"x": 0, "y": 0, "font": "s", "size": 10, "align": "left"}},
        },
        "fonts": {"s": "f.ttf"},
    }
    raw.update(overrides)
    return CertConfig.model_validate(raw)


def test_build_schema_one_table_per_round() -> None:
    cfg = _config(
        rounds=[
            {"id": "main", "label": "M", "table": "students", "pdf": "t.pdf"},
            {"id": "final", "label": "F", "table": "students_final", "pdf": "t2.pdf"},
        ]
    )
    tables = build_schema(cfg)
    assert [t.name for t in tables] == ["students", "students_final"]


def test_column_order_and_primary_key() -> None:
    cfg = _config()
    table = build_schema(cfg)[0]
    cols = [c.name for c in table.columns]
    assert cols[0] == "registration_number"  # sbd first
    assert table.columns[0].is_primary
    assert {"full_name", "date_of_birth", "school", "province"} <= set(cols)
    assert {"science_result", "english_result"} <= set(cols)


def test_schema_can_be_applied_to_real_sqlite(tmp_path) -> None:
    cfg = _config()
    sql = render_create_sql(build_schema(cfg))
    conn = sqlite3.connect(":memory:")
    conn.executescript(sql)
    rows = conn.execute("PRAGMA table_info(students)").fetchall()
    names = [r[1] for r in rows]
    assert names[0] == "registration_number"
    assert rows[0][5] == 1  # pk flag


def test_duplicate_table_names_rejected() -> None:
    cfg_raw = _config().model_dump()
    cfg_raw["rounds"] = [
        {"id": "a", "label": "A", "table": "students", "pdf": "p.pdf"},
        {"id": "b", "label": "B", "table": "students", "pdf": "p.pdf"},
    ]
    cfg = CertConfig.model_validate(cfg_raw)
    with pytest.raises(SchemaError, match="share the same table"):
        build_schema(cfg)


def test_subject_and_data_mapping_column_collision() -> None:
    """If a subject's db_col matches data_mapping.name_col, schema dedups (no duplicate columns)."""
    cfg = _config()
    raw = cfg.model_dump()
    raw["data_mapping"]["name_col"] = "science_result"  # collision with subject db_col
    cfg2 = CertConfig.model_validate(raw)
    tables = build_schema(cfg2)
    col_names = [c.name for c in tables[0].columns]
    assert col_names.count("science_result") == 1
