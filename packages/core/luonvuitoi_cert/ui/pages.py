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
    csp_nonce: str | None = None,
) -> str:
    """Render the public Certificate-Checker HTML.

    The page JavaScript POSTs the QR blob to ``verify_endpoint`` and renders
    the :class:`VerifyResponse` JSON. Blob may arrive via query string
    (``?blob=...``) from a scanned QR that encoded a URL into this page.
    """
    context = build_page_context(config, locale)
    context["verify_endpoint"] = verify_endpoint
    context["csp_nonce"] = csp_nonce
    return _render("certificate-checker.html.j2", context)


def render_student_portal_page(
    *,
    config: CertConfig,
    locale: Locale,
    search_endpoint: str = "/api/search",
    download_endpoint: str = "/api/download",
    captcha_endpoint: str = "/api/captcha",
    csp_nonce: str | None = None,
) -> str:
    """Render the public student-facing portal."""
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
            "csp_nonce": csp_nonce,
        }
    )
    return _render("index.html.j2", context)


def render_admin_page(
    *,
    config: CertConfig,
    locale: Locale,
    login_endpoint: str = "/api/admin/login",
    search_endpoint: str = "/api/search",
    csp_nonce: str | None = None,
) -> str:
    """Render the admin login + lightweight dashboard.

    ``csp_nonce`` is stamped onto the inline ``<script>`` when supplied so the
    transport layer can emit ``Content-Security-Policy: script-src 'nonce-…'``
    without having to rewrite the template.
    """
    context = build_page_context(config, locale)
    context.update(
        {
            "auth_mode": config.admin.auth_mode,
            "login_endpoint": login_endpoint,
            "search_endpoint": search_endpoint,
            "csp_nonce": csp_nonce,
        }
    )
    return _render("admin.html.j2", context)
