"""WSGI entrypoint for container/serverless deploys.

Gunicorn targets ``wsgi:app`` in the Dockerfile CMD. Vercel picks this up
via ``@vercel/python``. Reads ``PROJECT_ROOT`` (default ``/app/project``)
for the bind-mounted config + data directory.

M3 fix: previously inlined via ``RUN printf`` into /app/wsgi.py at Docker
image build time. Extracting to a real file lets editors + linters see it,
and prevents silent drift between dev and production entrypoints.
"""

from __future__ import annotations

import os
from pathlib import Path

from luonvuitoi_cert_cli.server import build_app

_ROOT = Path(os.environ.get("PROJECT_ROOT", "/app/project")).resolve()
app = build_app(_ROOT / "cert.config.json", _ROOT)
