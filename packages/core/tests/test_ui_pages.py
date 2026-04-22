"""Tests for the student-portal + admin-panel page renderers (Phase 10)."""

from __future__ import annotations

import pytest

from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.locale import load_locale
from luonvuitoi_cert.ui import render_admin_page, render_student_portal_page


def _cfg(**overrides) -> CertConfig:  # type: ignore[no-untyped-def]
    raw = {
        "project": {"name": "DEMO", "slug": "demo"},
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


# ── Student portal ──────────────────────────────────────────────────


def test_student_portal_renders_html() -> None:
    html = render_student_portal_page(config=_cfg(), locale=load_locale("en"))
    assert html.startswith("<!doctype html>")
    assert "Certificate Portal" in html
    assert "DEMO" in html


def test_portal_mode_name_dob_captcha_shows_dob_field() -> None:
    html = render_student_portal_page(
        config=_cfg(student_search={"mode": "name_dob_captcha"}),
        locale=load_locale("en"),
    )
    assert 'id="dob"' in html
    assert 'id="sbd"' in html
    assert "captcha-question" in html


def test_portal_mode_sbd_phone_omits_captcha() -> None:
    cfg = _cfg(
        student_search={"mode": "sbd_phone", "admin_mode": "sbd_auth"},
        data_mapping={"sbd_col": "sbd", "name_col": "name", "phone_col": "phone"},
    )
    html = render_student_portal_page(config=cfg, locale=load_locale("en"))
    assert 'id="phone"' in html
    assert 'id="captcha-answer"' not in html
    # JS should reflect disabled captcha too.
    assert "captchaRequired = false" in html or "captchaRequired=false" in html


def test_portal_mode_name_sbd_captcha_has_expected_fields() -> None:
    html = render_student_portal_page(
        config=_cfg(student_search={"mode": "name_sbd_captcha", "admin_mode": "sbd_auth"}),
        locale=load_locale("en"),
    )
    assert 'id="name"' in html
    assert 'id="sbd"' in html
    assert 'id="dob"' not in html  # wrong mode


def test_portal_escapes_project_name_for_xss() -> None:
    html = render_student_portal_page(
        config=_cfg(project={"name": "<script>hack()</script>", "slug": "x", "locale": "en"}),
        locale=load_locale("en"),
    )
    assert "<script>hack()</script>" not in html
    assert "&lt;script&gt;" in html


def test_portal_endpoints_are_tojson_safe() -> None:
    html = render_student_portal_page(
        config=_cfg(),
        locale=load_locale("en"),
        search_endpoint='/api/search"; alert(1); //',
    )
    # Unescaped closing quote followed by ; would break out of the JS literal.
    assert 'search";' not in html
    assert '\\"' in html


def test_portal_respects_vi_locale() -> None:
    html = render_student_portal_page(config=_cfg(), locale=load_locale("vi"))
    assert "Tra cứu" in html


# ── Admin panel ─────────────────────────────────────────────────────


def test_admin_page_password_mode() -> None:
    html = render_admin_page(
        config=_cfg(admin={"auth_mode": "password"}),
        locale=load_locale("en"),
    )
    assert 'id="password"' in html
    assert 'id="email"' in html


def test_admin_page_otp_mode_has_code_input() -> None:
    html = render_admin_page(
        config=_cfg(admin={"auth_mode": "otp_email"}),
        locale=load_locale("en"),
    )
    assert 'id="code"' in html
    assert 'id="password"' not in html


def test_admin_page_magic_link_mode_omits_secondary_fields() -> None:
    html = render_admin_page(
        config=_cfg(admin={"auth_mode": "magic_link"}),
        locale=load_locale("en"),
    )
    assert 'id="password"' not in html
    assert 'id="code"' not in html
    assert 'id="email"' in html


def test_admin_stashes_token_in_sessionstorage() -> None:
    html = render_admin_page(config=_cfg(), locale=load_locale("en"))
    assert "sessionStorage" in html
    assert "lvt_admin_token" in html


def test_admin_escapes_project_name() -> None:
    html = render_admin_page(
        config=_cfg(project={"name": "<b>hack</b>", "slug": "x", "locale": "en"}),
        locale=load_locale("en"),
    )
    assert "<b>hack</b>" not in html
    assert "&lt;b&gt;" in html


def test_admin_uses_configured_endpoints() -> None:
    html = render_admin_page(
        config=_cfg(),
        locale=load_locale("en"),
        login_endpoint="/custom/login",
        search_endpoint="/custom/search",
    )
    assert '"/custom/login"' in html
    assert '"/custom/search"' in html


def test_admin_exit_clears_lookup_state() -> None:
    """Regression: Phase 10 review B1 — sign-out must wipe the previous lookup."""
    html = render_admin_page(config=_cfg(), locale=load_locale("en"))
    exit_body = html.split("function exitDashboard")[1].split("function ")[0]
    assert "lookupFields.innerHTML" in exit_body
    assert "lookupResult.hidden = true" in exit_body
    assert 'lookupReason.textContent = ""' in exit_body


def test_student_portal_parses_rfc5987_filename() -> None:
    """Regression: Phase 10 review B2 — parseFilename must handle filename* form."""
    html = render_student_portal_page(config=_cfg(), locale=load_locale("en"))
    parser_body = html.split("function parseFilename")[1].split("function ")[0]
    assert "filename\\*" in parser_body
    assert "decodeURIComponent" in parser_body


@pytest.mark.parametrize(
    "mode,required",
    [
        ("name_dob_captcha", True),
        ("name_sbd_captcha", True),
        ("sbd_phone", False),
    ],
)
def test_captcha_block_matches_mode(mode: str, required: bool) -> None:
    cfg_raw = {
        "data_mapping": (
            {"sbd_col": "sbd", "name_col": "name", "dob_col": "dob"}
            if mode == "name_dob_captcha"
            else {"sbd_col": "sbd", "name_col": "name", "phone_col": "phone"}
            if mode == "sbd_phone"
            else {"sbd_col": "sbd", "name_col": "name"}
        ),
        "student_search": {"mode": mode, "admin_mode": "sbd_auth"},
    }
    html = render_student_portal_page(
        config=_cfg(**cfg_raw),
        locale=load_locale("en"),
    )
    has_captcha = 'id="captcha-answer"' in html
    assert has_captcha is required
