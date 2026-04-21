"""Guard: committed ``cert.schema.json`` must stay in sync with the generator.

Phase 02 review flagged that the committed schema had already drifted from
what ``scripts/export_schema.py`` produced. This test fails loudly on drift so
CI catches it before merge. If you edit ``models.py`` you **must** rerun
``python scripts/export_schema.py`` and commit the result.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from export_schema import render_schema  # type: ignore[import-not-found]  # noqa: E402

COMMITTED = REPO_ROOT / "cert.schema.json"


def test_committed_schema_matches_generator() -> None:
    expected = render_schema()
    actual = COMMITTED.read_text(encoding="utf-8")
    assert actual == expected, (
        "cert.schema.json is out of date — run `python scripts/export_schema.py` and commit the result."
    )
