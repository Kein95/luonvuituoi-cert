"""Vercel serverless entrypoint — single Flask app routed by ``vercel.json``.

Vercel's Python runtime loads the ``app`` symbol as a WSGI callable and
routes every incoming request through it. ``vercel.json`` rewrites all
paths to this file so page routes (``/``, ``/admin``, ``/certificate-
checker``) and API routes (``/api/...``) share the same dispatcher.

Set ``PROJECT_ROOT`` if your config lives anywhere other than the
repository root; otherwise the file two directories up from this module
is used.
"""

from __future__ import annotations

import os
from pathlib import Path

from luonvuitoi_cert_cli.server import build_app

_HERE = Path(__file__).resolve().parent
_ROOT = Path(os.environ.get("PROJECT_ROOT", _HERE.parent)).resolve()

# Build once at import time so cold-start cost doesn't land on the first
# request. The FontRegistry + KV backend live on the module's `app` closure
# and get reused across invocations within the same warm container.
app = build_app(_ROOT / "cert.config.json", _ROOT)
