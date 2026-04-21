"""Font registry: resolve TrueType fonts referenced by :class:`CertConfig.fonts`.

ReportLab's ``pdfmetrics.registerFont`` is a global singleton — registering
twice raises. This wrapper keeps track of what's already registered in the
current process so handlers can call :meth:`FontRegistry.ensure_loaded`
freely at request time without tripping over duplicate calls.
"""

from __future__ import annotations

import threading
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFError, TTFont

from luonvuitoi_cert.config import CertConfig


class FontRegistryError(Exception):
    """Raised when a font file referenced in the config is missing or invalid."""


class FontRegistry:
    """Resolve and register all fonts referenced by a :class:`CertConfig`.

    Paths in ``config.fonts`` are relative to ``project_root`` (the directory
    that owns the ``cert.config.json``). Missing files fail fast with a
    readable :class:`FontRegistryError` — never silently.

    Thread-safety: registration is serialized by a module-level lock so
    concurrent serverless invocations in the same process don't race when
    both see an unregistered font.
    """

    _lock = threading.Lock()
    _registered_globally: set[str] = set()

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
        """Register the font with ReportLab if not already registered; return the PSName."""
        if font_key in self._registered_globally:
            return font_key
        path = self.resolve(font_key)
        with self._lock:
            if font_key in self._registered_globally:
                return font_key
            try:
                pdfmetrics.registerFont(TTFont(font_key, str(path)))
            except TTFError as e:
                raise FontRegistryError(f"ReportLab rejected {path}: {e}") from e
            self._registered_globally.add(font_key)
        return font_key

    def ensure_all_loaded(self) -> None:
        """Eagerly load every font declared in the config. Useful at startup / tests."""
        for key in self._config.fonts:
            self.ensure_loaded(key)
