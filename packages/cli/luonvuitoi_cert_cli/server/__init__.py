"""Flask dev-server shim that wraps the pure handlers from ``luonvuitoi_cert``.

This subpackage exists only so ``lvt-cert dev`` has a minimal transport
layer locally. Production deployments use Vercel serverless functions
(Phase 15); both paths call the same pure-function handlers.
"""

from luonvuitoi_cert_cli.server.app import build_app

__all__ = ["build_app"]
