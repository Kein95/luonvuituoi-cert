"""UI template rendering — Jinja2 + config-driven branding.

Templates live under ``luonvuitoi_cert/templates/`` as ``.html.j2`` files and
ship with the package, so a deployed project doesn't need filesystem paths
to render them. Each public page has a thin render function (:mod:`ui.pages`)
that the transport layer (Flask dev server, Vercel handler) calls to produce
the HTML response.

Autoescape is always on — never mark a string safe that originated in a
config value or a user request without explicit justification.
"""

from luonvuitoi_cert.ui.pages import (
    PageRenderError,
    render_admin_page,
    render_certificate_checker_page,
    render_student_portal_page,
)
from luonvuitoi_cert.ui.templates import build_environment, build_page_context

__all__ = [
    "PageRenderError",
    "build_environment",
    "build_page_context",
    "render_admin_page",
    "render_certificate_checker_page",
    "render_student_portal_page",
]
