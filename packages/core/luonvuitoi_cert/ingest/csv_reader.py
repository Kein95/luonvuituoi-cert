"""Read students from a CSV file (stdlib ``csv`` + ``DictReader``).

UTF-8-with-BOM is transparently handled (``encoding="utf-8-sig"``) so Excel
exports work without a separate re-save step. Fields are stripped.
"""

from __future__ import annotations

import csv
from pathlib import Path

from luonvuitoi_cert.ingest.base import IngestError


def read_csv(path: str | Path) -> list[dict[str, str]]:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise IngestError(f"CSV file not found: {p}")
    try:
        text = p.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as e:
        raise IngestError(f"CSV file is not valid UTF-8 ({p}): {e.reason}") from e
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise IngestError(f"CSV file has no header row: {p}")
    out: list[dict[str, str]] = []
    for row in reader:
        cleaned = {k: (v or "").strip() for k, v in row.items() if k is not None}
        if all(v == "" for v in cleaned.values()):
            continue
        out.append(cleaned)
    return out
