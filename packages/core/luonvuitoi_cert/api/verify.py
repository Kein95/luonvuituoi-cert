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
) -> VerifyResponse:
    """Decode + verify the QR blob. Never raises — always returns a structured verdict."""
    if not config.features.qr_verify.enabled:
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
    public_key_path = Path(project_root) / config.features.qr_verify.public_key_path
    try:
        public_key = load_public_key(public_key_path)
    except SignatureError as e:
        raise VerifyError(str(e)) from e
    try:
        verify_payload(public_key, payload, signature)
    except SignatureError as e:
        return VerifyResponse(valid=False, reason=str(e), payload=payload)
    return VerifyResponse(valid=True, payload=payload)
