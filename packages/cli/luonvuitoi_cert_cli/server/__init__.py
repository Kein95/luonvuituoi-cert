"""Flask transport layer wrapping the pure handlers from ``luonvuitoi_cert``.

``build_app`` is the single WSGI application used by **every** runtime:
``lvt-cert dev`` locally, gunicorn in the Docker image (``wsgi.py``), and the
Vercel serverless entrypoint (the scaffold's ``api/index.py``). All of them
import ``build_app`` from here, so this subpackage is a production dependency,
not a dev-only convenience — keep it installed wherever the portal is served.
The handlers themselves live in ``luonvuitoi_cert`` and stay transport-agnostic.
"""

from luonvuitoi_cert_cli.server.app import build_app

__all__ = ["build_app"]
