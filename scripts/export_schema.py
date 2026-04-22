"""Export :class:`CertConfig` as a JSON Schema document.

Run this after editing ``models.py`` so editors pick up the new fields for
autocomplete. CI enforces equality between the committed ``cert.schema.json``
and the exporter output via ``test_schema_export_matches_committed``.

Importable without ``pip install -e`` thanks to the sys.path shim below — so
``python scripts/export_schema.py`` works in a fresh clone.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE_SRC = ROOT / "packages" / "core"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from luonvuitoi_cert.config.models import CertConfig  # noqa: E402

OUT = ROOT / "cert.schema.json"


def build_schema() -> dict:
    """Single source of truth for what the committed ``cert.schema.json`` should contain."""
    schema = CertConfig.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "LUONVUITUOI-CERT configuration"
    schema["$id"] = "https://kein95.github.io/luonvuituoi-cert/cert.schema.json"
    return schema


def render_schema() -> str:
    return json.dumps(build_schema(), indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    OUT.write_text(render_schema(), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
