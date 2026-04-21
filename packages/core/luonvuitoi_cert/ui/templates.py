"""Jinja environment builder + shared template context.

Templates ship inside the package (``luonvuitoi_cert/templates/``) so
:class:`PackageLoader` finds them without any filesystem config. Autoescape
is enabled for ``.html``/``.htm``/``.html.j2`` by default; we add ``.j2``
explicitly so our naming convention is covered.

``build_page_context`` builds the shared dict every page uses: branding,
locale strings, CSRF-style safety nonces (future use), and the config
project identifier. Keeping it centralized stops handlers from drifting.
"""

from __future__ import annotations

from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.locale import Locale

_AUTOESCAPE_EXTENSIONS = ("html", "htm", "xml", "j2", "html.j2")


def build_environment() -> Environment:
    """Return a Jinja environment bound to the package's ``templates/`` directory."""
    env = Environment(
        loader=PackageLoader("luonvuitoi_cert", "templates"),
        autoescape=select_autoescape(_AUTOESCAPE_EXTENSIONS),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    return env


def build_page_context(config: CertConfig, locale: Locale) -> dict[str, Any]:
    """Shared context dict every rendered page receives.

    Keep this small and stable — adding keys here touches every template.
    Things that vary per-page belong in the page renderer's extra context.
    """
    branding = config.project.branding
    return {
        "project": {
            "name": config.project.name,
            "slug": config.project.slug,
            "locale": config.project.locale,
        },
        "branding": {
            "logo_url": branding.logo_url or "",
            "primary_color": branding.primary_color,
            "accent_color": branding.accent_color,
        },
        "t": locale.get,
    }
