"""Tests for :mod:`luonvuitoi_cert.api.captcha`."""

from __future__ import annotations

import re
import time

import pytest

from luonvuitoi_cert.api.captcha import (
    CAPTCHA_TTL_SECONDS,
    KV_PREFIX,
    CaptchaError,
    issue_challenge,
    verify_challenge,
)


def _solve(question: str) -> int:
    a, op, b = re.match(r"(\d+)\s*([+\-×])\s*(\d+)", question).groups()  # type: ignore[union-attr]
    if op == "+":
        return int(a) + int(b)
    if op == "-":
        return int(a) - int(b)
    return int(a) * int(b)


def test_issue_and_verify_happy_path(kv_memory) -> None:  # type: ignore[no-untyped-def]
    ch = issue_challenge(kv_memory)
    verify_challenge(kv_memory, ch.id, _solve(ch.question))


def test_verify_consumes_challenge(kv_memory) -> None:  # type: ignore[no-untyped-def]
    ch = issue_challenge(kv_memory)
    verify_challenge(kv_memory, ch.id, _solve(ch.question))
    with pytest.raises(CaptchaError, match="not found"):
        verify_challenge(kv_memory, ch.id, _solve(ch.question))


def test_wrong_answer_raises(kv_memory) -> None:  # type: ignore[no-untyped-def]
    ch = issue_challenge(kv_memory)
    with pytest.raises(CaptchaError, match="incorrect"):
        verify_challenge(kv_memory, ch.id, _solve(ch.question) + 1)


def test_wrong_answer_still_consumes_challenge(kv_memory) -> None:  # type: ignore[no-untyped-def]
    """Replay protection: a single wrong guess invalidates the challenge."""
    ch = issue_challenge(kv_memory)
    with pytest.raises(CaptchaError):
        verify_challenge(kv_memory, ch.id, "bogus")
    with pytest.raises(CaptchaError, match="not found"):
        verify_challenge(kv_memory, ch.id, _solve(ch.question))


def test_non_integer_answer_raises(kv_memory) -> None:  # type: ignore[no-untyped-def]
    ch = issue_challenge(kv_memory)
    with pytest.raises(CaptchaError, match="not an integer"):
        verify_challenge(kv_memory, ch.id, "not a number")


def test_empty_id_raises(kv_memory) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(CaptchaError, match="required"):
        verify_challenge(kv_memory, "", "42")


def test_ttl_set(kv_memory) -> None:  # type: ignore[no-untyped-def]
    ch = issue_challenge(kv_memory)
    # Value is live immediately
    assert kv_memory.get(f"{KV_PREFIX}{ch.id}") is not None


def test_question_format(kv_memory) -> None:  # type: ignore[no-untyped-def]
    for _ in range(20):
        ch = issue_challenge(kv_memory)
        assert re.match(r"^\d+ [+\-×] \d+ = \?$", ch.question), ch.question
