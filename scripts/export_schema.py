"""Export :class:`CertConfig` as a JSON Schema document.

Run this after editing ``models.py`` so editors pick up the new fields for
autocomplete. CI should fail if the committed ``cert.schema.json`` diverges
from what this script produces.
"""

from __future__ import annotations

import json
from pathlib import Path

from luonvuitoi_cert.config.models import CertConfig

OUT = Path(__file__).resolve().parent.parent / "cert.schema.json"


def main() -> int:
    schema = CertConfig.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "LUONVUITUOI-CERT configuration"
    schema["$id"] = "https://luonvuitoi.github.io/cert/cert.schema.json"
    OUT.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
