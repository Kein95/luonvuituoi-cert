"""Opt-in shipment tracking.

When ``features.shipment.enabled`` is true, a ``shipments`` SQLite table is
created with fixed columns (``id``, ``round_id``, ``sbd``, ``status``,
``created_at``, ``updated_at``) plus one column per ``features.shipment.fields``
entry. Admins upsert records; students look up their own by SBD + round.
"""

from luonvuitoi_cert.shipment.repository import (
    ShipmentError,
    ShipmentRecord,
    get_shipment,
    list_shipments,
    upsert_shipment,
)
from luonvuitoi_cert.shipment.schema import build_shipment_schema, ensure_shipment_schema

__all__ = [
    "ShipmentError",
    "ShipmentRecord",
    "build_shipment_schema",
    "ensure_shipment_schema",
    "get_shipment",
    "list_shipments",
    "upsert_shipment",
]
