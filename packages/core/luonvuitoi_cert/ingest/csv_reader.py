"""Read students from a CSV file via the stdlib ``csv`` module.

UTF-8-with-BOM is transparently handled (``encoding="utf-8-sig"``) so Excel
exports work without a separate re-save step. The file is streamed through
``csv.DictReader`` with ``newline=""`` so quoted fields with embedded line
breaks (very common in Excel-exported CSVs) stay intact. Non-empty row cells
are ``.strip()``-ed, but falsy values like ``"0"`` and ``"False"`` pass
through unchanged.
"""

from __future__ import annotations

import csv
from pathlib import Path

from luonvuitoi_cert.ingest.base import IngestError


def read_csv(path: str | Path) -> list[dict[str, str]]:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise IngestError(f"CSV file not found: {p}")
    out: list[dict[str, str]] = []
    try:
        with p.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                raise IngestError(f"CSV file has no header row: {p}")
            for row in reader:
                cleaned = {k: (v.strip() if isinstance(v, str) else "") for k, v in row.items() if k}
                if all(v == "" for v in cleaned.values()):
                    continue
                out.append(cleaned)
    except UnicodeDecodeError as e:
        raise IngestError(f"CSV file is not valid UTF-8 ({p}): {e.reason}") from e
    except csv.Error as e:
        raise IngestError(f"CSV file is malformed ({p}): {e}") from e
    return out
