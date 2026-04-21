"""RSA-PSS-SHA256 signer + verifier for QR payloads.

Keys live on disk as PEM files. Signing happens on the issuer side (the
portal that mints certificates); verification needs only the public key and
runs both on the server ``/api/verify`` endpoint and, in theory, on any
offline client with the public key.
"""

from __future__ import annotations

from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.padding import PSS

from luonvuitoi_cert.qr.payload import QRPayload

_PADDING = PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=PSS.MAX_LENGTH)


class SignatureError(Exception):
    """Raised when a key can't be parsed, a signature is absent, or verification fails."""


def load_private_key(path: str | Path) -> rsa.RSAPrivateKey:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise SignatureError(f"private key not found: {p}")
    try:
        key = serialization.load_pem_private_key(p.read_bytes(), password=None)
    except (ValueError, TypeError) as e:
        raise SignatureError(f"private key at {p} is not a valid PEM RSA key: {e}") from e
    if not isinstance(key, rsa.RSAPrivateKey):
        raise SignatureError(f"private key at {p} is not RSA (got {type(key).__name__})")
    return key


def load_public_key(path: str | Path) -> rsa.RSAPublicKey:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise SignatureError(f"public key not found: {p}")
    try:
        key = serialization.load_pem_public_key(p.read_bytes())
    except (ValueError, TypeError) as e:
        raise SignatureError(f"public key at {p} is not a valid PEM RSA key: {e}") from e
    if not isinstance(key, rsa.RSAPublicKey):
        raise SignatureError(f"public key at {p} is not RSA (got {type(key).__name__})")
    return key


def sign_payload(private_key: rsa.RSAPrivateKey, payload: QRPayload) -> bytes:
    """Produce an RSA-PSS-SHA256 signature over the canonical JSON of ``payload``."""
    return private_key.sign(payload.to_canonical_json(), _PADDING, hashes.SHA256())


def verify_payload(public_key: rsa.RSAPublicKey, payload: QRPayload, signature: bytes) -> None:
    """Raise :class:`SignatureError` if the signature doesn't match the payload."""
    try:
        public_key.verify(signature, payload.to_canonical_json(), _PADDING, hashes.SHA256())
    except InvalidSignature as e:
        raise SignatureError("signature does not match payload") from e
