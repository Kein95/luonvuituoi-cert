"""Locale bundles for UI strings and error messages.

Built-in: ``en`` (default) and ``vi``. Projects can add more by dropping
``<locale>.json`` into their project root's ``locale/`` directory and passing
that path to :func:`load_locale`.
"""

from luonvuitoi_cert.locale.loader import Locale, LocaleError, load_locale

__all__ = ["Locale", "LocaleError", "load_locale"]
