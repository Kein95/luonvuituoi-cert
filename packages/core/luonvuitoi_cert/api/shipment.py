"""Shipment tracking handlers — admin upsert + public status lookup.

Admin path (``upsert_shipment_record``):
- Authenticates via :func:`verify_admin_token`; Viewer role rejected.
- Validates SBD; accepts ``status`` + an ``updates`` dict mapping
  config-declared field names to new values.
- Records a ``shipment.upsert`` entry in the activity log.

Public path (``lookup_shipment``):
- Anonymous student flow: name + SBD + CAPTCHA + rate limit, same gate as
  search (Phase 05). Returns only the sanitized status/fields dict — never
  the internal id or created_at.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from luonvuitoi_cert.api.captcha import verify_challenge
from luonvuitoi_cert.api.rate_limiter import check_rate_limit
from luonvuitoi_cert.api.security import SecurityError, validate_sbd
from luonvuitoi_cert.auth.activity_log import ActivityLog, log_admin_action
from luonvuitoi_cert.auth.admin_db import Role
from luonvuitoi_cert.auth.tokens import TokenError, verify_admin_token
from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.shipment import ShipmentError, ShipmentRecord, get_shipment, upsert_shipment
from luonvuitoi_cert.storage.kv.base import KVBackend

PUBLIC_LOOKUP_RATE_LIMIT = 20
PUBLIC_LOOKUP_WINDOW_SECONDS = 60


class ShipmentHandlerError(Exception):
    """Raised when a handler can't proceed (feature disabled, unknown target, bad input)."""


@dataclass(slots=True)
class ShipmentLookupResponse:
    status: str
    updated_at: str
    fields: dict[str, str]


def _require_enabled(config: CertConfig) -> None:
    if not config.features.shipment.enabled:
        raise ShipmentHandlerError("shipment tracking is disabled for this project")


def _require_round(config: CertConfig, round_id: str) -> None:
    if not any(r.id == round_id for r in config.rounds):
        raise ShipmentHandlerError(
            f"unknown round_id {round_id!r}; available: {[r.id for r in config.rounds]}"
        )


def upsert_shipment_record(
    *,
    config: CertConfig,
    db_path: str | Path,
    activity: ActivityLog,
    params: dict[str, Any],
    client_ip: str | None = None,
    env: dict[str, str] | None = None,
) -> ShipmentRecord:
    """Admin entry point — write-through for shipment state. Audits every change."""
    _require_enabled(config)
    try:
        token = verify_admin_token(str(params.get("token", "")), env=env)
    except TokenError as e:
        raise ShipmentHandlerError(str(e)) from e
    # Allowlist — any future role (e.g. Role.AUDITOR) starts read-only until
    # explicitly opted-in, instead of silently inheriting write access.
    if token.role not in (Role.ADMIN, Role.SUPER_ADMIN):
        raise ShipmentHandlerError(f"role {token.role.value!r} cannot update shipments")

    sbd = validate_sbd(params.get("sbd"))
    round_id = str(params.get("round_id", "")).strip()
    status = str(params.get("status", "")).strip()
    updates_raw = params.get("updates") or {}
    if not isinstance(updates_raw, dict):
        raise SecurityError("updates must be an object mapping field names to values")
    if not round_id or not status:
        raise ShipmentHandlerError("round_id and status are both required")
    _require_round(config, round_id)

    try:
        record = upsert_shipment(
            db_path,
            config,
            round_id=round_id,
            sbd=sbd,
            status=status,
            fields=updates_raw,
        )
    except ShipmentError as e:
        raise ShipmentHandlerError(str(e)) from e

    # Record which fields were touched but not the raw values — tracking codes
    # and addresses shouldn't flow through the webhook-forwarded audit trail.
    log_admin_action(
        activity,
        user_id=token.user_id,
        user_email=token.email,
        action="shipment.upsert",
        target_id=f"{round_id}:{sbd}",
        metadata={"status": status, "fields_touched": sorted(updates_raw.keys())},
        ip=client_ip,
    )
    return record


def lookup_shipment(
    *,
    config: CertConfig,
    db_path: str | Path,
    kv: KVBackend,
    params: dict[str, Any],
    client_id: str,
) -> ShipmentLookupResponse:
    """Public student lookup — CAPTCHA + rate-limit gated.

    Intentionally returns only (status, updated_at, fields) — no internal ids,
    no timestamps beyond ``updated_at`` — so scrapers can't harvest the admin
    record shape.
    """
    _require_enabled(config)
    sbd = validate_sbd(params.get("sbd"))
    round_id = str(params.get("round_id", "")).strip()
    if not round_id:
        raise ShipmentHandlerError("round_id is required")
    _require_round(config, round_id)

    verify_challenge(kv, str(params.get("captcha_id", "")), params.get("captcha_answer"))
    check_rate_limit(
        kv,
        "shipment_lookup",
        client_id,
        limit=PUBLIC_LOOKUP_RATE_LIMIT,
        window_seconds=PUBLIC_LOOKUP_WINDOW_SECONDS,
    )

    record = get_shipment(db_path, config, round_id=round_id, sbd=sbd)
    if record is None:
        raise ShipmentHandlerError("no shipment recorded for this certificate yet")
    # Only fields the operator explicitly allowlisted leave the server —
    # defaults to empty, so a fresh deploy doesn't leak tracking codes.
    public_keys = set(config.features.shipment.public_fields)
    safe_fields = {k: v for k, v in record.fields.items() if k in public_keys}
    return ShipmentLookupResponse(
        status=record.status,
        updated_at=record.updated_at,
        fields=safe_fields,
    )
