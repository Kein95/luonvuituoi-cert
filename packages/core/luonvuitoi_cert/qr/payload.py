"""Serialized representation of a signed certificate.

Keep the field set small and stable — every added key needs a corresponding
update in every existing QR in the wild, or legacy certs will fail to verify.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class QRPayload:
    """What gets signed and embedded in the QR.

    ``project_slug`` binds the signature to its issuer — a malicious portal
    can't reuse our public key to validate certs from another deployment.
    """

    project_slug: str
    round_id: str
    subject_code: str
    result: str
    sbd: str
    issued_at: int  # Unix seconds

    @classmethod
    def now(
        cls,
        *,
        project_slug: str,
        round_id: str,
        subject_code: str,
        result: str,
        sbd: str,
        clock=None,  # type: ignore[no-untyped-def]
    ) -> "QRPayload":
        return cls(
            project_slug=project_slug,
            round_id=round_id,
            subject_code=subject_code,
            result=result,
            sbd=sbd,
            issued_at=int((clock or time.time)()),
        )

    def to_canonical_json(self) -> bytes:
        """Sort keys + no whitespace so signature is byte-stable across runtimes."""
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode("utf-8")

    @classmethod
    def from_json(cls, blob: bytes | str) -> "QRPayload":
        data = json.loads(blob)
        return cls(
            project_slug=str(data["project_slug"]),
            round_id=str(data["round_id"]),
            subject_code=str(data["subject_code"]),
            result=str(data["result"]),
            sbd=str(data["sbd"]),
            issued_at=int(data["issued_at"]),
        )
