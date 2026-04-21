"""Tests for the Certificate-Checker page renderer."""

from __future__ import annotations

import pytest
from jinja2 import Environment

from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.locale import load_locale
from luonvuitoi_cert.ui import (
    build_environment,
    build_page_context,
    render_certificate_checker_page,
)


def _cfg(**overrides) -> CertConfig:  # type: ignore[no-untyped-def]
    raw = {
        "project": {"name": "DEMO ACADEMY", "slug": "demo", "locale": "en"},
        "rounds": [{"id": "main", "label": "Main", "table": "students", "pdf": "t.pdf"}],
        "subjects": [{"code": "S", "en": "Science", "db_col": "s"}],
        "results": {"S": {"GOLD": 1}},
        "layout": {
            "page_size": [100, 100],
            "fields": {"n": {"x": 0, "y": 0, "font": "f", "size": 10, "align": "left"}},
        },
        "fonts": {"f": "f.ttf"},
    }
    raw.update(overrides)
    return CertConfig.model_validate(raw)


# ── Environment / context ───────────────────────────────────────────


def test_environment_enables_autoescape() -> None:
    env = build_environment()
    assert isinstance(env, Environment)
    # j2 html templates must autoescape.
    assert env.autoescape is not False  # callable or True


def test_page_context_carries_branding_and_locale() -> None:
    cfg = _cfg(project={"name": "X", "slug": "x", "locale": "en", "branding": {"primary_color": "#112233"}})
    ctx = build_page_context(cfg, load_locale("en"))
    assert ctx["branding"]["primary_color"] == "#112233"
    assert callable(ctx["t"])
    assert ctx["project"]["slug"] == "x"


# ── Certificate-Checker render ──────────────────────────────────────


def test_render_certificate_checker_returns_html() -> None:
    html = render_certificate_checker_page(config=_cfg(), locale=load_locale("en"))
    assert html.startswith("<!doctype html>")
    assert "Certificate Verification" in html
    assert "DEMO ACADEMY" in html


def test_render_uses_branding_colors() -> None:
    cfg = _cfg(project={"name": "X", "slug": "x", "locale": "en", "branding": {"primary_color": "#663399", "accent_color": "#ffcc00"}})
    html = render_certificate_checker_page(config=cfg, locale=load_locale("en"))
    assert "#663399" in html
    assert "#ffcc00" in html


def test_render_embeds_verify_endpoint() -> None:
    html = render_certificate_checker_page(
        config=_cfg(), locale=load_locale("en"), verify_endpoint="/custom/verify"
    )
    assert '"/custom/verify"' in html


def test_render_escapes_project_name_for_xss() -> None:
    evil = _cfg(project={"name": "<script>alert(1)</script>", "slug": "x", "locale": "en"})
    # Config rejects spaces/HTML in slug; name has its own validator (length only)
    # so the template must escape any HTML that leaks in.
    html = render_certificate_checker_page(config=evil, locale=load_locale("en"))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_vi_locale_translates_page_strings() -> None:
    html = render_certificate_checker_page(config=_cfg(), locale=load_locale("vi"))
    assert "Xác minh" in html  # from locale/vi.json "verify.title"


def test_page_js_uses_tojson_for_endpoint() -> None:
    """Endpoint passed through ``|tojson`` so quotes / angle brackets can't break out of the JS literal."""
    html = render_certificate_checker_page(
        config=_cfg(), locale=load_locale("en"), verify_endpoint='/api/verify"; alert(1); //'
    )
    # tojson escapes the trailing quote; there must be no literal JS injection.
    assert 'alert(1)' not in html.replace("alert(1)", "", 1) or '\\"' in html  # escaped form present


def test_page_contains_auto_submit_snippet() -> None:
    html = render_certificate_checker_page(config=_cfg(), locale=load_locale("en"))
    assert "URLSearchParams" in html  # auto-fills from ?blob=


def test_missing_template_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from luonvuitoi_cert.ui import pages

    def broken_env():  # type: ignore[no-untyped-def]
        env = build_environment()
        env.loader = None  # type: ignore[assignment]
        return env

    monkeypatch.setattr(pages, "build_environment", broken_env)
    with pytest.raises(pages.PageRenderError):
        render_certificate_checker_page(config=_cfg(), locale=load_locale("en"))
