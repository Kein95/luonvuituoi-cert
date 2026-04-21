"""Passwordless login via one-time URL token delivered by email.

Flow: admin requests magic link → server mints a URL-safe token, stores
``(email, expires_at)`` in KV keyed by hash(token) → email delivers a URL
containing the plaintext token → admin clicks → :func:`verify_magic_link`
atomically consumes the KV entry and returns the email to the login
dispatcher.
"""

from __future__ import annotations

import hashlib
import secrets

from luonvuitoi_cert.auth.email import EmailMessage, EmailProvider
from luonvuitoi_cert.storage.kv.base import KVBackend

MAGIC_LINK_TTL_SECONDS = 15 * 60
KV_PREFIX = "magic:"


class MagicLinkError(Exception):
    """Raised when a magic-link token is missing, consumed, expired, or mismatched."""


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_magic_link(
    kv: KVBackend,
    email_provider: EmailProvider,
    *,
    email: str,
    link_builder,  # type: ignore[no-untyped-def]
    subject: str = "Your admin sign-in link",
) -> str:
    """Mint a token, stash its hash + the email in KV, email the URL.

    ``link_builder(token: str) -> str`` produces the click URL; the handler
    supplies this because the scheme/host differ between environments. The
    plaintext token never lives server-side.
    """
    email = email.strip().lower()
    if "@" not in email:
        raise MagicLinkError(f"invalid email: {email!r}")
    token = secrets.token_urlsafe(32)
    kv.set(f"{KV_PREFIX}{_hash_token(token)}", email, ttl_seconds=MAGIC_LINK_TTL_SECONDS)
    url = link_builder(token)
    email_provider.send(
        EmailMessage(
            to=email,
            subject=subject,
            text=(
                f"Click to sign in: {url}\n\n"
                f"This link expires in {MAGIC_LINK_TTL_SECONDS // 60} minutes and can only be used once."
            ),
        )
    )
    return token


def verify_magic_link(kv: KVBackend, token: str) -> str:
    """Atomically consume; return the email the token was minted for."""
    if not token:
        raise MagicLinkError("magic-link token is required")
    email = kv.consume(f"{KV_PREFIX}{_hash_token(token)}")
    if email is None:
        raise MagicLinkError("magic link expired or already used")
    return email
