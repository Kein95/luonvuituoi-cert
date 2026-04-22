"""Read students from a JSON file shaped as a list of objects.

Accepts either a bare list-of-dicts (``[{"name": ...}, ...]``) or an
envelope (``{"records": [...]}``, ``{"data": [...]}``, or ``{"students":
[...]}``). Non-string cell values are stringified so downstream schemas stay
uniform.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from luonvuitoi_cert.ingest.base import IngestError

_ENVELOPE_KEYS = ("records", "data", "students", "rows")


def _unwrap(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in _ENVELOPE_KEYS:
            if isinstance(raw.get(key), list):
                return raw[key]  # type: ignore[no-any-return]
    raise IngestError(
        f"JSON root must be a list or an object with one of {_ENVELOPE_KEYS!r}; got {type(raw).__name__}"
    )


def read_json(path: str | Path) -> list[dict[str, str]]:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise IngestError(f"JSON file not found: {p}")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise IngestError(f"JSON file is malformed ({p}): {e.msg} at line {e.lineno}") from e
    records = _unwrap(raw)

    out: list[dict[str, str]] = []
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            raise IngestError(f"JSON record #{i} is not an object (type={type(rec).__name__})")
        out.append({str(k): "" if v is None else str(v).strip() for k, v in rec.items()})
    return out
