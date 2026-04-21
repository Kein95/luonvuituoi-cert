"""Public ``/api/verify`` handler for the Certificate-Checker page.

Accepts the opaque blob a scanner extracted from the printed QR, validates
the signature with the config-provided public key, and returns a structured
verdict the UI renders. The endpoint is unauthenticated by design — anyone
holding a printed certificate must be able to confirm it.

Transport-layer contract: the HTTP wrapper **must** call
:func:`validate_request_size` on the raw body before JSON-parsing it, and
apply rate limiting on a per-IP basis (verification is cheap, but abuse is
easy to reduce).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.qr import (
    CodecError,
    QRPayload,
    SignatureError,
    decode_blob,
    load_public_key,
    verify_payload,
)

_LOGGER = logging.getLogger(__name__)


class VerifyError(Exception):
    """Raised when the endpoint can't even attempt verification (missing config, etc.)."""


@dataclass(slots=True)
class VerifyResponse:
    valid: bool
    reason: str | None = None
    payload: QRPayload | None = None

    def to_json_safe(self) -> dict[str, object]:
        """Serialize for HTTP response, omitting internal exception shapes."""
        result: dict[str, object] = {"valid": self.valid}
        if self.reason:
            result["reason"] = self.reason
        if self.payload is not None:
            result["payload"] = {
                "project_slug": self.payload.project_slug,
                "round_id": self.payload.round_id,
                "subject_code": self.payload.subject_code,
                "result": self.payload.result,
                "sbd": self.payload.sbd,
                "issued_at": self.payload.issued_at,
            }
        return result


def verify_qr(
    *,
    config: CertConfig,
    project_root: str | Path,
    blob: str,
    clock=None,  # type: ignore[no-untyped-def]
) -> VerifyResponse:
    """Decode + verify the QR blob. Never raises on bad client input — always returns a verdict.

    :class:`VerifyError` is raised only for operational misconfiguration
    (QR disabled, missing public key) so the transport layer can respond with
    a distinct HTTP status. The exception message is caller-safe — it never
    contains filesystem paths or raw key material.
    """
    qr_cfg = config.features.qr_verify
    if not qr_cfg.enabled:
        raise VerifyError("QR verification is disabled for this project")
    if not blob:
        return VerifyResponse(valid=False, reason="missing QR payload")
    try:
        payload, signature = decode_blob(blob)
    except CodecError as e:
        return VerifyResponse(valid=False, reason=f"malformed QR payload: {e}")
    if payload.project_slug != config.project.slug:
        # Signed for a different project — treat as tampered rather than valid.
        return VerifyResponse(
            valid=False,
            reason=(
                f"project mismatch: QR claims {payload.project_slug!r}, "
                f"this portal is {config.project.slug!r}"
            ),
            payload=payload,
        )
    public_key_path = Path(project_root) / qr_cfg.public_key_path
    try:
        public_key = load_public_key(public_key_path)
    except SignatureError as e:
        # Don't leak the resolved filesystem path to the caller.
        _LOGGER.error("verify_qr: public key load failed (%s): %s", public_key_path, e)
        raise VerifyError("verifier is not configured correctly") from e
    try:
        verify_payload(public_key, payload, signature)
    except SignatureError as e:
        return VerifyResponse(valid=False, reason=str(e), payload=payload)
    if qr_cfg.max_age_seconds > 0:
        now = int((clock or time.time)())
        age = now - payload.issued_at
        if age > qr_cfg.max_age_seconds:
            return VerifyResponse(
                valid=False,
                reason=f"certificate expired ({age}s old > {qr_cfg.max_age_seconds}s)",
                payload=payload,
            )
        if age < -60:  # allow small clock skew
            return VerifyResponse(
                valid=False,
                reason="certificate issued in the future; clock skew or forged timestamp",
                payload=payload,
            )
    return VerifyResponse(valid=True, payload=payload)
