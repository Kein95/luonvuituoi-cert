"""Tests for ingest readers: Excel, CSV, JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from openpyxl import Workbook

from luonvuitoi_cert.ingest import IngestError, read_csv, read_excel, read_json


# ── Excel ───────────────────────────────────────────────────────────


def _write_excel(path: Path, rows: list[list[object]]) -> None:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    wb.save(path)


def test_excel_reads_header_and_rows(tmp_path: Path) -> None:
    p = tmp_path / "in.xlsx"
    _write_excel(p, [["sbd", "name"], ["001", "Alice"], ["002", "Bob"]])
    assert read_excel(p) == [{"sbd": "001", "name": "Alice"}, {"sbd": "002", "name": "Bob"}]


def test_excel_blank_rows_dropped(tmp_path: Path) -> None:
    p = tmp_path / "in.xlsx"
    _write_excel(p, [["sbd", "name"], ["001", "A"], [None, None], ["002", "B"]])
    assert len(read_excel(p)) == 2


def test_excel_integer_floats_coerced_to_int_string(tmp_path: Path) -> None:
    p = tmp_path / "in.xlsx"
    _write_excel(p, [["sbd", "name"], [12345, "A"]])
    assert read_excel(p)[0]["sbd"] == "12345"  # not "12345.0"


def test_excel_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="not found"):
        read_excel(tmp_path / "absent.xlsx")


# ── CSV ─────────────────────────────────────────────────────────────


def test_csv_reads_header_and_rows(tmp_path: Path) -> None:
    p = tmp_path / "in.csv"
    p.write_text("sbd,name\n001,Alice\n002,Bob\n", encoding="utf-8")
    assert read_csv(p) == [{"sbd": "001", "name": "Alice"}, {"sbd": "002", "name": "Bob"}]


def test_csv_utf8_bom_stripped(tmp_path: Path) -> None:
    p = tmp_path / "in.csv"
    p.write_text("\ufeffsbd,name\n001,A\n", encoding="utf-8")
    rows = read_csv(p)
    assert list(rows[0].keys()) == ["sbd", "name"]  # BOM not in the first key


def test_csv_empty_rows_dropped(tmp_path: Path) -> None:
    p = tmp_path / "in.csv"
    p.write_text("sbd,name\n001,A\n,\n002,B\n", encoding="utf-8")
    assert len(read_csv(p)) == 2


def test_csv_preserves_quoted_multiline_fields(tmp_path: Path) -> None:
    """Regression: Phase 04 review H1 — text.splitlines() joined lines inside quotes."""
    p = tmp_path / "in.csv"
    # Write bytes directly to avoid Windows newline translation altering the fixture.
    p.write_bytes(b'sbd,note\n001,"line1\nline2\nline3"\n')
    rows = read_csv(p)
    # Normalize to compare — csv.reader may return \n or \r\n depending on platform/newline args.
    assert rows[0]["note"].replace("\r\n", "\n") == "line1\nline2\nline3"


def test_csv_preserves_falsy_strings(tmp_path: Path) -> None:
    p = tmp_path / "in.csv"
    p.write_text("sbd,score\n001,0\n002,False\n", encoding="utf-8")
    rows = read_csv(p)
    assert rows[0]["score"] == "0"
    assert rows[1]["score"] == "False"


def test_csv_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="not found"):
        read_csv(tmp_path / "absent.csv")


# ── JSON ────────────────────────────────────────────────────────────


def test_json_list_root(tmp_path: Path) -> None:
    p = tmp_path / "in.json"
    p.write_text(json.dumps([{"sbd": "001", "name": "Alice"}]), encoding="utf-8")
    assert read_json(p) == [{"sbd": "001", "name": "Alice"}]


def test_json_envelope_records(tmp_path: Path) -> None:
    p = tmp_path / "in.json"
    p.write_text(json.dumps({"records": [{"sbd": "1"}]}), encoding="utf-8")
    assert read_json(p) == [{"sbd": "1"}]


def test_json_envelope_students(tmp_path: Path) -> None:
    p = tmp_path / "in.json"
    p.write_text(json.dumps({"students": [{"sbd": "1"}]}), encoding="utf-8")
    assert read_json(p) == [{"sbd": "1"}]


def test_json_integer_values_stringified(tmp_path: Path) -> None:
    p = tmp_path / "in.json"
    p.write_text(json.dumps([{"sbd": 12345, "score": 100}]), encoding="utf-8")
    row = read_json(p)[0]
    assert row["sbd"] == "12345"
    assert row["score"] == "100"


def test_json_null_values_become_empty_string(tmp_path: Path) -> None:
    p = tmp_path / "in.json"
    p.write_text(json.dumps([{"sbd": "1", "phone": None}]), encoding="utf-8")
    assert read_json(p)[0]["phone"] == ""


def test_json_unexpected_root_raises(tmp_path: Path) -> None:
    p = tmp_path / "in.json"
    p.write_text(json.dumps("just a string"), encoding="utf-8")
    with pytest.raises(IngestError, match="root must be"):
        read_json(p)


def test_json_non_object_record_raises(tmp_path: Path) -> None:
    p = tmp_path / "in.json"
    p.write_text(json.dumps([["a", "b"]]), encoding="utf-8")
    with pytest.raises(IngestError, match="not an object"):
        read_json(p)
