"""Certificate rendering engine: fonts + PDF overlay primitives.

The engine is deliberately *stateless and config-driven*. Handlers pass in a
:class:`CertConfig` plus per-student values; the engine turns those into a
signed, ready-to-download PDF. No filesystem side effects beyond reading the
template PDF and the font files referenced by the config.
"""

from luonvuitoi_cert.engine.fonts import FontRegistry, FontRegistryError
from luonvuitoi_cert.engine.renderer import (
    OverlayError,
    OverlayRequest,
    render_certificate_bytes,
)

__all__ = [
    "FontRegistry",
    "FontRegistryError",
    "OverlayError",
    "OverlayRequest",
    "render_certificate_bytes",
]
