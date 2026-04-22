"""Tiny i18n: load a locale bundle JSON and look up dotted keys.

No templating, no plurals, no gender — just string substitution. If a project
needs more, it can wrap a real library (gettext, Fluent). For now this covers
the CLI output, UI labels, and error messages without bringing in a
dependency.
"""

from __future__ import annotations

import json
from pathlib import Path
from string import Template
from typing import Any

BUILTIN_DIR = Path(__file__).resolve().parent
DEFAULT_LOCALE = "en"


def _substitute(value: str, kwargs: dict[str, Any]) -> str:
    """Apply ``$name`` / ``${name}`` substitution without exposing ``str.format`` internals.

    We deliberately avoid ``str.format`` because translator-supplied strings
    could otherwise walk attributes (``{x.__class__}``) or trigger DoS-sized
    alignment specs (``{x:>10000000}``). ``string.Template.safe_substitute``
    is a flat substitution with no format specs, attributes, or indexing.
    """
    if not kwargs:
        return value
    return Template(value).safe_substitute({k: str(v) for k, v in kwargs.items()})


class LocaleError(Exception):
    """Raised when a locale JSON is missing or malformed."""


class Locale:
    """In-memory view of one locale bundle (loaded JSON dict)."""

    def __init__(self, code: str, data: dict[str, Any], fallback: Locale | None = None) -> None:
        self.code = code
        self._data = data
        self._fallback = fallback

    def get(self, key: str, default: str | None = None, **kwargs: Any) -> str:
        """Look up ``"a.b.c"`` in the bundle; format with ``kwargs`` if present.

        Falls through to the fallback locale (if any), then to ``default``,
        then to ``key`` itself so missing keys are obvious in the UI.
        """
        node: Any = self._data
        for segment in key.split("."):
            if isinstance(node, dict) and segment in node:
                node = node[segment]
            else:
                node = None
                break
        if isinstance(node, str):
            return _substitute(node, kwargs)
        if self._fallback is not None:
            return self._fallback.get(key, default, **kwargs)
        if default is not None:
            return _substitute(default, kwargs)
        return key


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise LocaleError(f"locale file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise LocaleError(f"locale file is not valid JSON ({path}): {e.msg} at line {e.lineno}") from e
    if not isinstance(data, dict):
        raise LocaleError(f"locale root must be an object, got {type(data).__name__}")
    return data


def load_locale(code: str, search_dirs: list[Path] | None = None) -> Locale:
    """Load ``<code>.json`` from the first matching directory, chaining to ``en`` as fallback."""
    dirs = [*(search_dirs or []), BUILTIN_DIR]
    bundle_path = next((d / f"{code}.json" for d in dirs if (d / f"{code}.json").exists()), None)
    if bundle_path is None:
        raise LocaleError(f"locale {code!r} not found (searched: {[str(d) for d in dirs]})")
    data = _load_json(bundle_path)
    if code == DEFAULT_LOCALE:
        return Locale(code, data)
    fallback = load_locale(DEFAULT_LOCALE, search_dirs)
    return Locale(code, data, fallback=fallback)
