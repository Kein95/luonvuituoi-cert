"""Tests for :mod:`luonvuitoi_cert.locale`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from luonvuitoi_cert.locale import Locale, LocaleError, load_locale


def test_builtin_en_loads() -> None:
    loc = load_locale("en")
    assert loc.code == "en"
    assert loc.get("portal.title") == "Certificate Portal"


def test_builtin_vi_loads_and_translates() -> None:
    loc = load_locale("vi")
    assert loc.get("portal.title") == "Cổng Chứng chỉ"


def test_vi_falls_back_to_en_for_missing_key() -> None:
    loc = load_locale("vi")
    # Key not present in either bundle — must return the key itself as final fallback.
    assert loc.get("completely.missing.key") == "completely.missing.key"


def test_missing_key_with_explicit_default() -> None:
    loc = load_locale("en")
    assert loc.get("no.such.key", default="N/A") == "N/A"


def test_format_substitutes_kwargs(tmp_path: Path) -> None:
    bundle = tmp_path / "en.json"
    bundle.write_text(json.dumps({"greet": "Hello {name}"}), encoding="utf-8")
    loc = load_locale("en", search_dirs=[tmp_path])
    assert loc.get("greet", name="Alice") == "Hello Alice"


def test_project_override_takes_precedence(tmp_path: Path) -> None:
    (tmp_path / "en.json").write_text(json.dumps({"portal": {"title": "Custom"}}), encoding="utf-8")
    loc = load_locale("en", search_dirs=[tmp_path])
    assert loc.get("portal.title") == "Custom"


def test_unknown_locale_raises() -> None:
    with pytest.raises(LocaleError, match="not found"):
        load_locale("xx")


def test_malformed_json_raises(tmp_path: Path) -> None:
    (tmp_path / "en.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(LocaleError, match="not valid JSON"):
        load_locale("en", search_dirs=[tmp_path])


def test_root_must_be_object(tmp_path: Path) -> None:
    (tmp_path / "en.json").write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(LocaleError, match="must be an object"):
        load_locale("en", search_dirs=[tmp_path])


def test_direct_locale_construction() -> None:
    loc = Locale("ja", {"a": {"b": "ok"}})
    assert loc.get("a.b") == "ok"
    assert loc.get("a") == "a"  # node resolves to dict, not string → fallback
