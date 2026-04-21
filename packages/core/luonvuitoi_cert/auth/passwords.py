"""Password hashing via stdlib PBKDF2-SHA256.

No bcrypt / argon2 dependency on purpose — stdlib is enough for the threat
model of a small-org admin panel, and it keeps the serverless cold-start
cheap. Hashes are stored in modular format ``pbkdf2$<iter>$<salt_b64>$<hash_b64>``
so future migrations (argon2id) can coexist by sniffing the prefix.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

ALGO = "pbkdf2"
ITERATIONS = 200_000
SALT_BYTES = 16
HASH_BYTES = 32


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded + padding)


def hash_password(password: str, *, iterations: int = ITERATIONS) -> str:
    """Return a PBKDF2-SHA256 hash usable with :func:`verify_password`.

    The plaintext is encoded as UTF-8; callers should NFKC-normalize ahead of
    time if they want ``café`` to hash the same regardless of compose/decompose
    form.
    """
    if not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, HASH_BYTES)
    return f"{ALGO}${iterations}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of ``password`` against a stored PBKDF2 hash.

    Malformed stored hashes, empty passwords, or unknown algorithms all
    return ``False`` rather than raising — callers shouldn't leak the reason
    a login failed, and we already returned ``False`` on correct-password-but-
    corrupted-row before catching up to the typical wrong-password timing.
    """
    if not password or not stored:
        return False
    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != ALGO:
        return False
    try:
        iterations = int(parts[1])
        salt = _b64decode(parts[2])
        expected = _b64decode(parts[3])
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, len(expected))
    return hmac.compare_digest(actual, expected)
