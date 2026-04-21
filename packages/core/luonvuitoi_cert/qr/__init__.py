"""QR verification pipeline: RSA-PSS signer + PNG codec + verifier.

The issuer (the portal generating certificates) signs a JSON payload
describing the certificate, concatenates payload and signature in a URL-safe
blob, and renders that blob into a PNG QR. Anyone holding the certificate
can scan the QR and hit ``/api/verify`` — the server re-derives the payload,
validates the signature with the *public* key, and reports whether the
document is authentic.

Encryption is intentionally not layered on top. The payload only contains
non-sensitive identifiers (SBD, round, subject, result, project slug,
issued_at); confidentiality adds complexity without meaningfully improving
the threat model. Signature alone prevents forgery.
"""

from luonvuitoi_cert.qr.codec import (
    CodecError,
    decode_blob,
    encode_blob,
    render_qr_png,
)
from luonvuitoi_cert.qr.payload import QRPayload
from luonvuitoi_cert.qr.signer import (
    SignatureError,
    load_private_key,
    load_public_key,
    sign_payload,
    verify_payload,
)

__all__ = [
    "CodecError",
    "QRPayload",
    "SignatureError",
    "decode_blob",
    "encode_blob",
    "load_private_key",
    "load_public_key",
    "render_qr_png",
    "sign_payload",
    "verify_payload",
]
