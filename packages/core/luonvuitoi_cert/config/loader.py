"""Load and validate ``cert.config.json`` from disk.

Kept separate from the models module so scaffolder tools can import the
Pydantic classes without dragging in filesystem/JSON concerns (and vice
versa).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from luonvuitoi_cert.config.models import CertConfig


class ConfigError(Exception):
    """Raised when a config file is missing, malformed JSON, or fails validation."""


def _format_validation_error(err: ValidationError, source: str | None = None) -> str:
    """Render a :class:`ValidationError` as a short, user-friendly message.

    Drops the ``https://errors.pydantic.dev/...`` hint that Pydantic appends to
    every error (noisy for end users) and never echoes the raw input (which may
    contain secrets). Groups multiple errors with a leading bullet per field.
    """
    header = f"cert.config.json failed validation ({source})" if source else "cert.config.json failed validation"
    lines = [header + ":"]
    for e in err.errors():
        loc = ".".join(str(p) for p in e.get("loc", ())) or "<root>"
        lines.append(f"  - {loc}: {e.get('msg', 'invalid value')}")
    return "\n".join(lines)


def load_config_dict(raw: dict[str, Any], *, source: str | None = None) -> CertConfig:
    """Validate an already-decoded dict and return a :class:`CertConfig`.

    ``$schema`` is stripped transparently so authors can point their JSON at
    ``cert.schema.json`` for editor autocomplete without tripping strict
    ``extra="forbid"`` validation.
    """
    cleaned = {k: v for k, v in raw.items() if k != "$schema"}
    try:
        return CertConfig.model_validate(cleaned)
    except ValidationError as e:
        raise ConfigError(_format_validation_error(e, source)) from e


def load_config(path: str | Path) -> CertConfig:
    """Read ``path``, parse JSON, and return a validated :class:`CertConfig`.

    Raises :class:`ConfigError` with a readable message for any failure mode so
    the CLI can surface it without exposing a traceback to end users.
    """
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise ConfigError(f"config file not found: {p}")
    if not p.is_file():
        raise ConfigError(f"config path is not a file: {p}")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except UnicodeDecodeError as e:
        raise ConfigError(f"config file is not valid UTF-8 ({p}): {e.reason}") from e
    except json.JSONDecodeError as e:
        raise ConfigError(f"config file is not valid JSON ({p}): {e.msg} at line {e.lineno}") from e
    if not isinstance(raw, dict):
        raise ConfigError(f"config root must be a JSON object, got {type(raw).__name__}")
    return load_config_dict(raw, source=str(p))
