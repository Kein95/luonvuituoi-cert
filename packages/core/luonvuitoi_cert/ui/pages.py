"""Per-page render helpers. Each one returns a fully-rendered HTML string."""

from __future__ import annotations

from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.locale import Locale
from luonvuitoi_cert.ui.templates import build_environment, build_page_context


class PageRenderError(Exception):
    """Raised when a template can't be rendered (missing file, bad context)."""


def _render(template_name: str, context: dict) -> str:
    env = build_environment()
    try:
        template = env.get_template(template_name)
    except Exception as e:  # noqa: BLE001
        raise PageRenderError(f"{template_name} template not found: {e}") from e
    return template.render(context)


def render_certificate_checker_page(
    *,
    config: CertConfig,
    locale: Locale,
    verify_endpoint: str = "/api/verify",
) -> str:
    """Render the public Certificate-Checker HTML.

    The page JavaScript POSTs the QR blob to ``verify_endpoint`` and renders
    the :class:`VerifyResponse` JSON. Blob may arrive via query string
    (``?blob=...``) from a scanned QR that encoded a URL into this page.
    """
    context = build_page_context(config, locale)
    context["verify_endpoint"] = verify_endpoint
    return _render("certificate-checker.html.j2", context)


def render_student_portal_page(
    *,
    config: CertConfig,
    locale: Locale,
    search_endpoint: str = "/api/search",
    download_endpoint: str = "/api/download",
    captcha_endpoint: str = "/api/captcha",
) -> str:
    """Render the public student-facing portal.

    The form fields are driven by ``config.student_search.mode``; the CAPTCHA
    block is shown whenever the mode demands it (every mode except
    ``sbd_phone``). All three endpoints are customizable because transport-
    layer glue in Phase 11/15 may prefix routes.
    """
    mode = config.student_search.mode
    captcha_required = mode != "sbd_phone"
    context = build_page_context(config, locale)
    context.update(
        {
            "search_mode": mode,
            "captcha_required": captcha_required,
            "search_endpoint": search_endpoint,
            "download_endpoint": download_endpoint,
            "captcha_endpoint": captcha_endpoint,
        }
    )
    return _render("index.html.j2", context)


def render_admin_page(
    *,
    config: CertConfig,
    locale: Locale,
    login_endpoint: str = "/api/admin/login",
    search_endpoint: str = "/api/search",
) -> str:
    """Render the admin login + lightweight dashboard.

    Login form fields track ``config.admin.auth_mode`` (password / otp_email /
    magic_link). A successful login stashes the JWT in ``sessionStorage`` so
    an accidental page reload doesn't force a re-login mid-session.
    """
    context = build_page_context(config, locale)
    context.update(
        {
            "auth_mode": config.admin.auth_mode,
            "login_endpoint": login_endpoint,
            "search_endpoint": search_endpoint,
        }
    )
    return _render("admin.html.j2", context)
