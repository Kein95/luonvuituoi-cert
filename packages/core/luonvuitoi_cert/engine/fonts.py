"""Font registry: resolve TrueType fonts referenced by :class:`CertConfig.fonts`.

ReportLab's ``pdfmetrics.registerFont`` is a global singleton keyed on the
font's PostScript name. If two projects in the same process both use
``"serif"`` as a config key but point at different TTF files, registering the
second one would be a no-op and the first file would silently win. To avoid
that, every ``(font_key, resolved_path)`` pair is registered under a
path-derived PSName so distinct files can coexist; callers receive the actual
PSName back from :meth:`ensure_loaded` and pass it to ``canvas.setFont``.
"""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFError, TTFont

from luonvuitoi_cert.config import CertConfig


class FontRegistryError(Exception):
    """Raised when a font file referenced in the config is missing or invalid."""


def _psname_for(font_key: str, resolved_path: Path) -> str:
    """Return a unique PostScript name derived from ``(key, path)``.

    Deterministic so repeated loads of the same file produce the same name.
    """
    digest = hashlib.sha1(str(resolved_path).encode("utf-8")).hexdigest()[:8]
    return f"{font_key}_{digest}"


class FontRegistry:
    """Resolve and register all fonts referenced by a :class:`CertConfig`.

    Paths in ``config.fonts`` are relative to ``project_root`` (the directory
    that owns the ``cert.config.json``). Missing files fail fast with a
    readable :class:`FontRegistryError` — never silently.

    Thread-safety: registration is serialized by a module-level lock so
    concurrent serverless invocations in the same process don't race when
    both see an unregistered font.

    Collision-safety: ``(font_key, resolved_path)`` is the cache key, so two
    projects using the same config key with different TTFs register under
    different PSNames and both work correctly.
    """

    _lock = threading.Lock()
    _psname_by_path: dict[tuple[str, str], str] = {}

    def __init__(self, config: CertConfig, project_root: str | Path) -> None:
        self._config = config
        self._root = Path(project_root).expanduser().resolve()

    def resolve(self, font_key: str) -> Path:
        """Return the absolute path of the font registered under ``font_key``."""
        try:
            rel = self._config.fonts[font_key]
        except KeyError as e:
            raise FontRegistryError(
                f"font key {font_key!r} not declared in config.fonts "
                f"(available: {sorted(self._config.fonts)})"
            ) from e
        path = (self._root / rel).resolve()
        if not path.exists():
            raise FontRegistryError(f"font file missing: {path} (from config.fonts[{font_key!r}])")
        if not path.is_file():
            raise FontRegistryError(f"font path is not a file: {path}")
        return path

    def ensure_loaded(self, font_key: str) -> str:
        """Register the font with ReportLab if not already registered and return the PSName.

        The PSName is path-derived, so callers must use this return value (not
        the raw ``font_key``) when calling ``canvas.setFont``.
        """
        path = self.resolve(font_key)
        cache_key = (font_key, str(path))
        cached = self._psname_by_path.get(cache_key)
        if cached is not None:
            return cached
        psname = _psname_for(font_key, path)
        with self._lock:
            cached = self._psname_by_path.get(cache_key)
            if cached is not None:
                return cached
            try:
                pdfmetrics.registerFont(TTFont(psname, str(path)))
            except TTFError as e:
                raise FontRegistryError(f"ReportLab rejected {path}: {e}") from e
            self._psname_by_path[cache_key] = psname
        return psname

    def ensure_all_loaded(self) -> None:
        """Eagerly load every font declared in the config. Useful at startup / tests."""
        for key in self._config.fonts:
            self.ensure_loaded(key)
