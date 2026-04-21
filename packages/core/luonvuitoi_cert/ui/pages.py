"""Per-page render helpers. Each one returns a fully-rendered HTML string."""

from __future__ import annotations

from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.locale import Locale
from luonvuitoi_cert.ui.templates import build_environment, build_page_context


class PageRenderError(Exception):
    """Raised when a template can't be rendered (missing file, bad context)."""


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
    env = build_environment()
    context = build_page_context(config, locale)
    context["verify_endpoint"] = verify_endpoint
    try:
        template = env.get_template("certificate-checker.html.j2")
    except Exception as e:  # noqa: BLE001
        raise PageRenderError(f"certificate-checker template not found: {e}") from e
    return template.render(context)
