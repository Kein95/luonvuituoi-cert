"""Login dispatcher — consumes a credential payload, returns a signed JWT.

Three flavors share the same response shape so callers don't branch on mode:

- ``password`` — ``{"email", "password"}`` → ``verify_admin_password``
- ``otp_email`` — two-step: first call seeds ``{"email"}``; second call
  verifies ``{"email", "code"}``
- ``magic_link`` — two-step: first call seeds ``{"email"}``; second call
  consumes ``{"token"}``

Missing credentials or wrong guesses raise :class:`LoginError` with a
deliberately vague message; unknown-email vs wrong-password distinctions are
hidden from external callers but logged for operators.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from luonvuitoi_cert.auth.activity_log import ActivityLog, log_admin_action
from luonvuitoi_cert.auth.admin_db import AdminUser, get_admin_user, verify_admin_password
from luonvuitoi_cert.auth.email import EmailProvider
from luonvuitoi_cert.auth.magic_link import MagicLinkError, issue_magic_link, verify_magic_link
from luonvuitoi_cert.auth.otp import OTPError, issue_otp, verify_otp
from luonvuitoi_cert.auth.tokens import issue_admin_token
from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.storage.kv.base import KVBackend

_LOGGER = logging.getLogger(__name__)


def _burn_equivalent_kv_write(kv: KVBackend, email: str) -> None:
    """Write to a decoy KV key + compute a dummy hash so unknown-user request timing matches.

    Closes the user-enumeration timing oracle in OTP / magic-link flows — step 1
    takes roughly the same wall-clock regardless of whether the email maps to
    an active admin. Actual email delivery happens only for real users, but
    the outward-facing response is identical (``challenge_issued=True``).
    """
    decoy_code = secrets.token_urlsafe(6)
    hashlib.sha256(f"{email}|{decoy_code}".encode("utf-8")).hexdigest()
    kv.set(
        f"decoy:{secrets.token_urlsafe(12)}",
        decoy_code,
        ttl_seconds=60,
    )


class LoginError(Exception):
    """Raised for every form of failed authentication. Message is caller-safe."""


@dataclass(slots=True)
class LoginResponse:
    """One shape for every login outcome.

    ``token`` is populated on success (password or second-step OTP / magic).
    ``challenge_issued`` is True for the first step of OTP / magic-link flows
    where the server has completed the challenge-issue path (a real email is
    sent only for registered users, but the response shape is identical for
    unknown inputs to close the user-enumeration timing oracle).
    """

    token: str | None = None
    user: AdminUser | None = None
    challenge_issued: bool = False


def _mint(
    user: AdminUser, env: dict[str, str] | None, activity: ActivityLog | None, ip: str | None
) -> LoginResponse:
    token = issue_admin_token(user_id=user.id, email=user.email, role=user.role, env=env)
    if activity is not None:
        log_admin_action(
            activity,
            user_id=user.id,
            user_email=user.email,
            action="admin.login.success",
            metadata={"role": user.role.value},
            ip=ip,
        )
    return LoginResponse(token=token, user=user)


def _log_failure(
    activity: ActivityLog | None,
    *,
    email: str,
    reason: str,
    ip: str | None,
) -> None:
    if activity is None:
        return
    log_admin_action(
        activity,
        user_id=None,
        user_email=email or None,
        action="admin.login.failure",
        metadata={"reason": reason},
        ip=ip,
    )


def perform_login(
    config: CertConfig,
    *,
    db_path: str | Path,
    kv: KVBackend,
    email_provider: EmailProvider,
    params: dict[str, Any],
    env: dict[str, str] | None = None,
    magic_link_builder=None,  # type: ignore[no-untyped-def]
    activity: ActivityLog | None = None,
    ip: str | None = None,
) -> LoginResponse:
    """Dispatch to the configured auth mode. Raises :class:`LoginError` on failure.

    ``activity`` (optional): if supplied, ``admin.login.success`` and
    ``admin.login.failure`` events are written to the audit trail. ``ip`` is
    the caller's client IP, passed through to the log entry.
    """
    mode = config.admin.auth_mode
    email = str(params.get("email", "")).strip().lower()

    if mode == "password":
        password = str(params.get("password", ""))
        if not email or not password:
            _log_failure(activity, email=email, reason="missing-credentials", ip=ip)
            raise LoginError("email and password are required")
        user = verify_admin_password(db_path, email=email, password=password)
        if user is None:
            _LOGGER.info("admin login failed (password) for %s", email)
            _log_failure(activity, email=email, reason="bad-password", ip=ip)
            raise LoginError("invalid credentials")
        return _mint(user, env, activity, ip)

    if mode == "otp_email":
        if not email:
            _log_failure(activity, email=email, reason="missing-email", ip=ip)
            raise LoginError("email is required")
        code = params.get("code")
        if code is None:
            # Step 1: always return a uniform response so user-existence is not
            # distinguishable from the outside. Email only goes to real users.
            user = get_admin_user(db_path, email=email)
            if user is not None and user.is_active:
                issue_otp(kv, email_provider, email=email)
            else:
                _LOGGER.info("admin OTP requested for unknown/inactive %s", email)
                _burn_equivalent_kv_write(kv, email)
            return LoginResponse(challenge_issued=True)
        try:
            verify_otp(kv, email=email, code=str(code))
        except OTPError as e:
            _LOGGER.info("admin OTP verify failed for %s: %s", email, e)
            _log_failure(activity, email=email, reason="bad-otp", ip=ip)
            raise LoginError("invalid credentials") from e
        user = get_admin_user(db_path, email=email)
        if user is None or not user.is_active:
            _log_failure(activity, email=email, reason="otp-ok-but-inactive", ip=ip)
            raise LoginError("invalid credentials")
        return _mint(user, env, activity, ip)

    if mode == "magic_link":
        token = params.get("token")
        if token is None:
            if not email:
                _log_failure(activity, email=email, reason="missing-email", ip=ip)
                raise LoginError("email is required to request a magic link")
            if magic_link_builder is None:
                raise LoginError("magic_link_builder is required when issuing a magic link")
            user = get_admin_user(db_path, email=email)
            if user is not None and user.is_active:
                issue_magic_link(kv, email_provider, email=email, link_builder=magic_link_builder)
            else:
                _LOGGER.info("admin magic-link requested for unknown/inactive %s", email)
                _burn_equivalent_kv_write(kv, email)
            return LoginResponse(challenge_issued=True)
        try:
            resolved_email = verify_magic_link(kv, str(token))
        except MagicLinkError as e:
            _LOGGER.info("admin magic-link verify failed: %s", e)
            _log_failure(activity, email="", reason="bad-magic-link", ip=ip)
            raise LoginError("invalid credentials") from e
        user = get_admin_user(db_path, email=resolved_email)
        if user is None or not user.is_active:
            _log_failure(activity, email=resolved_email, reason="magic-ok-but-inactive", ip=ip)
            raise LoginError("invalid credentials")
        return _mint(user, env, activity, ip)

    raise LoginError(f"unknown admin.auth_mode: {mode!r}")
