"""Security primitives shared by every API handler.

Small, stateless helpers — the kind of thing that's tempting to copy-paste
between handlers until they drift. Living here as named functions makes it
obvious when they change and keeps the handlers focused on their own logic.
"""

from __future__ import annotations

import os
import re
import unicodedata

DEFAULT_ALLOWED_ORIGINS = ("*",)
"""Opt-in wildcard for the public student portal.

Projects that need to lock origins down override via ``ALLOWED_ORIGINS`` env
var (comma-separated) before import. Handlers read :func:`get_allowed_origins`
so it picks up mutations during testing without module reloads.
"""

MAX_REQUEST_BYTES_DEFAULT = 32 * 1024

_SBD_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_UNSAFE_FS_CHARS = re.compile(r'[\x00-\x1f<>:"/\\|?*]+')
_MULTI_WS = re.compile(r"\s+")


class SecurityError(Exception):
    """Raised when a request body violates a size / format invariant."""


def get_allowed_origins() -> tuple[str, ...]:
    raw = os.environ.get("ALLOWED_ORIGINS", "").strip()
    if not raw:
        return DEFAULT_ALLOWED_ORIGINS
    return tuple(x.strip() for x in raw.split(",") if x.strip())


def clean_sbd(value: object) -> str:
    """Normalize a user-supplied SBD before validation or lookup.

    Accepts ``int``/``float`` (from Excel), strips whitespace, drops a
    decimal-zero suffix (``"12345.0" → "12345"``). Does *not* validate — use
    :func:`validate_sbd` afterwards.
    """
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if "." in text and text.replace(".", "", 1).isdigit() and text.endswith(".0"):
        return text[:-2]
    return text


def validate_sbd(value: object) -> str:
    """Return the cleaned SBD or raise :class:`SecurityError`.

    Enforces the same character class the config schema demands of
    ``data_mapping.sbd_col`` values: alphanumerics plus ``_-``, no path
    separators, max 64 chars.
    """
    cleaned = clean_sbd(value)
    if not cleaned:
        raise SecurityError("sbd is required")
    if not _SBD_RE.match(cleaned):
        raise SecurityError(f"sbd has invalid characters: {cleaned!r}")
    return cleaned


def validate_request_size(body: bytes, *, max_bytes: int = MAX_REQUEST_BYTES_DEFAULT) -> None:
    """Bound request bodies so handlers can't be asked to parse a gigabyte of JSON."""
    if len(body) > max_bytes:
        raise SecurityError(f"request body too large ({len(body)} > {max_bytes})")


def sanitize_filename(name: str, *, default: str = "certificate.pdf") -> str:
    """Make ``name`` safe for ``Content-Disposition`` + filesystem use.

    Strips path separators, control chars, collapses whitespace. Applies
    NFKC normalization so visually-identical Unicode variants don't sneak
    in different byte sequences.
    """
    if not name:
        return default
    normalized = unicodedata.normalize("NFKC", name)
    cleaned = _UNSAFE_FS_CHARS.sub("_", normalized)
    cleaned = _MULTI_WS.sub(" ", cleaned).strip(" .")
    return cleaned or default
