"""Shared UTC timestamp helper for the shipment package.

Single source of truth so ``shipment_history`` and ``shipment_draft`` rows
can't drift apart if the format ever changes.
"""

from __future__ import annotations

import time


def iso_now() -> str:
    """Return the current UTC time as an ISO-8601 ``...Z`` string."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
