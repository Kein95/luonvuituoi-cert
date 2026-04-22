"""One-time password (6-digit numeric) via email.

Flow: admin requests OTP → server stores ``hash(code)`` in KV keyed by email
with 5-min TTL → email delivers the plaintext code → admin submits →
:func:`verify_otp` atomically consumes and compares in constant time.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from luonvuitoi_cert.auth.email import EmailMessage, EmailProvider
from luonvuitoi_cert.storage.kv.base import KVBackend

OTP_TTL_SECONDS = 300
OTP_DIGITS = 6
KV_PREFIX = "otp:"


class OTPError(Exception):
    """Raised when an OTP lookup fails, expires, or miscompares."""


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_code(code: str, email: str) -> str:
    """Salt the code with the email so two users can't collide on the same digits."""
    return hashlib.sha256(f"{email}|{code}".encode()).hexdigest()


def issue_otp(
    kv: KVBackend, email_provider: EmailProvider, *, email: str, subject: str = "Your verification code"
) -> str:
    """Generate, store hashed, and email a fresh 6-digit code. Returns the ID client submits with verify."""
    email = _normalize_email(email)
    if "@" not in email:
        raise OTPError(f"invalid email: {email!r}")
    code = "".join(secrets.choice("0123456789") for _ in range(OTP_DIGITS))
    kv.set(f"{KV_PREFIX}{email}", _hash_code(code, email), ttl_seconds=OTP_TTL_SECONDS)
    email_provider.send(
        EmailMessage(
            to=email,
            subject=subject,
            text=f"Your code is {code}. It expires in {OTP_TTL_SECONDS // 60} minutes.",
        )
    )
    return email  # the "challenge id" the client echoes back with the code


def verify_otp(kv: KVBackend, *, email: str, code: str) -> None:
    """Atomically consume + compare. Raises :class:`OTPError` on any mismatch."""
    email = _normalize_email(email)
    if not code:
        raise OTPError("otp code is required")
    stored = kv.consume(f"{KV_PREFIX}{email}")
    if stored is None:
        raise OTPError("otp expired or unknown")
    submitted_hash = _hash_code(code.strip(), email)
    if not hmac.compare_digest(stored, submitted_hash):
        raise OTPError("otp is incorrect")
