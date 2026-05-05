"""Read-only access to vendored static assets shipped inside the package.

Assets live under ``luonvuitoi_cert/static/`` and are served by the dispatcher
at ``GET /static/<name>``. We deliberately keep the lookup minimal:

* No filesystem traversal: ``name`` must be a flat filename — separators,
  parent references, or hidden dotfiles are rejected before resolution.
* MIME inferred from suffix; only a small allowlist is recognized so an
  attacker can't smuggle ``Content-Type: text/html`` past the dispatcher.
* The file must exist *inside* the package directory (resolved via
  ``importlib.resources``) — symlinks pointing outside are not followed
  because the resource API doesn't expose them.
"""

from __future__ import annotations

import re
from importlib import resources

_PACKAGE = "luonvuitoi_cert.static"
_VALID_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_MIME_BY_SUFFIX = {
    ".js": "application/javascript",
    ".css": "text/css",
    ".map": "application/json",
}


class StaticAssetError(Exception):
    """Raised when a requested asset is missing, hidden, or has a bad name."""


def read_static_asset(name: str) -> tuple[bytes, str]:
    """Return ``(bytes, content_type)`` for ``name`` or raise StaticAssetError.

    ``name`` is the bare filename (e.g. ``"jsqr.min.js"``) — never a path.
    """
    if not name or not _VALID_NAME.match(name):
        raise StaticAssetError(f"invalid asset name: {name!r}")
    suffix_idx = name.rfind(".")
    if suffix_idx <= 0:
        raise StaticAssetError(f"asset has no extension: {name!r}")
    content_type = _MIME_BY_SUFFIX.get(name[suffix_idx:].lower())
    if content_type is None:
        raise StaticAssetError(f"asset suffix not allowed: {name!r}")
    try:
        package_root = resources.files(_PACKAGE)
    except (ModuleNotFoundError, FileNotFoundError) as exc:
        raise StaticAssetError(f"static package missing: {exc}") from exc
    target = package_root.joinpath(name)
    if not target.is_file():
        raise StaticAssetError(f"asset not found: {name!r}")
    return target.read_bytes(), content_type
