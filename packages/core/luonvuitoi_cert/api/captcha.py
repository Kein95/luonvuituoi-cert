"""Arithmetic CAPTCHA backed by the KV store.

Trade-off: tiny math problems aren't accessibility-friendly and can be solved
by OCR bots. But they're zero-dependency, zero-vendor, and stop the trivial
scrape attempts that plague public certificate portals. If a project outgrows
them, swap in hCaptcha / Turnstile by writing a new :func:`verify_challenge`.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Protocol

from luonvuitoi_cert.storage.kv.base import KVBackend

CAPTCHA_TTL_SECONDS = 300
KV_PREFIX = "captcha:"


class CaptchaError(Exception):
    """Raised when a challenge is unknown, expired, or fails to verify."""


class _Op(Protocol):
    symbol: str

    def apply(self, a: int, b: int) -> int: ...


@dataclass(frozen=True, slots=True)
class _AddOp:
    symbol: str = "+"

    def apply(self, a: int, b: int) -> int:
        return a + b


@dataclass(frozen=True, slots=True)
class _SubOp:
    symbol: str = "-"

    def apply(self, a: int, b: int) -> int:
        return a - b


@dataclass(frozen=True, slots=True)
class _MulOp:
    symbol: str = "×"

    def apply(self, a: int, b: int) -> int:
        return a * b


_OPS: tuple[_Op, ...] = (_AddOp(), _SubOp(), _MulOp())


@dataclass(frozen=True, slots=True)
class CaptchaChallenge:
    """What the server hands to the client — *not* the answer."""

    id: str
    question: str


def issue_challenge(kv: KVBackend, *, rng: secrets.SystemRandom | None = None) -> CaptchaChallenge:
    """Create a fresh challenge, store the expected answer in KV, return the question."""
    gen = rng or secrets.SystemRandom()
    op = gen.choice(_OPS)
    if isinstance(op, _MulOp):
        a = gen.randint(2, 6)
        b = gen.randint(2, 6)
    elif isinstance(op, _SubOp):
        a = gen.randint(5, 15)
        b = gen.randint(1, a)  # non-negative result
    else:
        a = gen.randint(2, 9)
        b = gen.randint(2, 9)

    answer = op.apply(a, b)
    cid = secrets.token_urlsafe(16)
    kv.set(f"{KV_PREFIX}{cid}", str(answer), ttl_seconds=CAPTCHA_TTL_SECONDS)
    return CaptchaChallenge(id=cid, question=f"{a} {op.symbol} {b} = ?")


def verify_challenge(kv: KVBackend, challenge_id: str, answer: object) -> None:
    """Consume the challenge — raises :class:`CaptchaError` on any mismatch.

    Consumption is single-use and race-safe: the KV entry is atomically
    read-and-deleted via ``consume()``. Two concurrent requests with the same
    correct answer cannot both succeed, and replays of a correct answer never
    work twice — even across backends with independent transactions.
    """
    if not challenge_id:
        raise CaptchaError("captcha id is required")
    expected = kv.consume(f"{KV_PREFIX}{challenge_id}")
    if expected is None:
        raise CaptchaError("captcha challenge not found or expired")
    try:
        submitted = int(str(answer).strip())
    except (TypeError, ValueError) as e:
        raise CaptchaError(f"captcha answer is not an integer: {answer!r}") from e
    if submitted != int(expected):
        raise CaptchaError("captcha answer is incorrect")
