"""Tests for :mod:`luonvuitoi_cert.ingest.orchestrator`."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.ingest import IngestError, ingest_rows


def _cfg() -> CertConfig:
    return CertConfig.model_validate(
        {
            "project": {"name": "T", "slug": "t"},
            "rounds": [{"id": "main", "label": "M", "table": "students", "pdf": "t.pdf"}],
            "subjects": [{"code": "S", "en": "Science", "db_col": "science_result"}],
            "results": {"S": {"GOLD": 1}},
            "data_mapping": {
                "sbd_col": "sbd",
                "name_col": "full_name",
                "school_col": "school",
                "extra_cols": ["province"],
            },
            "layout": {
                "page_size": [100, 100],
                "fields": {"n": {"x": 0, "y": 0, "font": "f", "size": 10, "align": "left"}},
            },
            "fonts": {"f": "f.ttf"},
        }
    )


def _fetch(db: Path, table: str) -> list[dict]:
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(f'SELECT * FROM "{table}"').fetchall()]
    conn.close()
    return rows


def test_happy_path_inserts_all_rows(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "test.db"
    rows = [
        {"sbd": "001", "full_name": "Alice", "school": "A", "province": "X", "science_result": "GOLD"},
        {"sbd": "002", "full_name": "Bob", "school": "B", "province": "Y", "science_result": "GOLD"},
    ]
    result = ingest_rows(cfg, db, "main", rows)
    assert result.rows_inserted == 2
    assert result.rows_skipped == 0
    stored = _fetch(db, "students")
    assert {r["sbd"] for r in stored} == {"001", "002"}
    assert stored[0]["full_name"] == "Alice"


def test_unknown_columns_dropped_declared_missing_are_blank(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "test.db"
    rows = [{"sbd": "001", "full_name": "Alice", "extraneous_col": "ignored"}]
    ingest_rows(cfg, db, "main", rows)
    stored = _fetch(db, "students")[0]
    assert "extraneous_col" not in stored
    assert stored["province"] == ""  # declared but missing in source


def test_missing_sbd_row_skipped_with_warning(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "test.db"
    rows = [
        {"sbd": "001", "full_name": "A"},
        {"sbd": "", "full_name": "Bob"},  # SBD missing
        {"full_name": "Charlie"},  # SBD key absent
    ]
    result = ingest_rows(cfg, db, "main", rows)
    assert result.rows_inserted == 1
    assert result.rows_skipped == 2
    assert len(result.warnings) == 2


def test_duplicate_sbd_warn_mode_keeps_first(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "test.db"
    rows = [
        {"sbd": "001", "full_name": "Alice"},
        {"sbd": "001", "full_name": "Alice2"},
    ]
    result = ingest_rows(cfg, db, "main", rows, on_duplicate="warn")
    assert result.rows_inserted == 1
    assert result.rows_skipped == 1
    assert any("duplicate" in w.lower() for w in result.warnings)
    stored = _fetch(db, "students")
    assert stored[0]["full_name"] == "Alice"  # first wins


def test_duplicate_sbd_skip_mode_silent(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "test.db"
    rows = [
        {"sbd": "001", "full_name": "Alice"},
        {"sbd": "001", "full_name": "Alice2"},
    ]
    result = ingest_rows(cfg, db, "main", rows, on_duplicate="skip")
    assert result.rows_inserted == 1
    assert result.rows_skipped == 1
    assert not result.warnings


def test_duplicate_sbd_replace_mode_overwrites(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "test.db"
    rows = [
        {"sbd": "001", "full_name": "Alice"},
        {"sbd": "001", "full_name": "Alice2"},
    ]
    result = ingest_rows(cfg, db, "main", rows, on_duplicate="replace")
    assert result.rows_inserted == 2
    assert result.rows_skipped == 0
    stored = _fetch(db, "students")
    assert stored[0]["full_name"] == "Alice2"


def test_unknown_round_raises(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "test.db"
    with pytest.raises(IngestError, match="round_id"):
        ingest_rows(cfg, db, "bogus", [])


def test_idempotent_schema_creation(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "test.db"
    ingest_rows(cfg, db, "main", [{"sbd": "001", "full_name": "A"}])
    # Second call on the same DB must not crash (CREATE TABLE IF NOT EXISTS).
    result = ingest_rows(cfg, db, "main", [{"sbd": "002", "full_name": "B"}])
    assert result.rows_inserted == 1


def test_sbd_is_stripped(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "test.db"
    ingest_rows(cfg, db, "main", [{"sbd": "  001  ", "full_name": "A"}])
    assert _fetch(db, "students")[0]["sbd"] == "001"


def test_falsy_numeric_values_preserved(tmp_path: Path) -> None:
    """Regression: Phase 04 review C1 — 0 / False / 0.0 used to become empty strings."""
    cfg = _cfg()
    db = tmp_path / "test.db"
    ingest_rows(
        cfg,
        db,
        "main",
        [
            {"sbd": "001", "full_name": "A", "science_result": 0},
            {"sbd": "002", "full_name": "B", "science_result": False},
            {"sbd": "003", "full_name": "C", "science_result": 0.0},
        ],
    )
    stored = {r["sbd"]: r["science_result"] for r in _fetch(db, "students")}
    assert stored["001"] == "0"
    assert stored["002"] == "False"
    assert stored["003"] == "0.0"


def test_none_value_stays_blank(tmp_path: Path) -> None:
    cfg = _cfg()
    db = tmp_path / "test.db"
    ingest_rows(cfg, db, "main", [{"sbd": "001", "full_name": "A", "science_result": None}])
    assert _fetch(db, "students")[0]["science_result"] == ""
