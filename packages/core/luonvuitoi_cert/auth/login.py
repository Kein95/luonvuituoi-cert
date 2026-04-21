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

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from luonvuitoi_cert.auth.admin_db import AdminUser, get_admin_user, verify_admin_password
from luonvuitoi_cert.auth.email import EmailProvider
from luonvuitoi_cert.auth.magic_link import MagicLinkError, issue_magic_link, verify_magic_link
from luonvuitoi_cert.auth.otp import OTPError, issue_otp, verify_otp
from luonvuitoi_cert.auth.tokens import issue_admin_token
from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.storage.kv.base import KVBackend

_LOGGER = logging.getLogger(__name__)


class LoginError(Exception):
    """Raised for every form of failed authentication. Message is caller-safe."""


@dataclass(slots=True)
class LoginResponse:
    """One shape for every login outcome.

    ``token`` is populated on success (password or second-step OTP / magic).
    ``challenge_issued`` is True for the first step of OTP / magic-link flows
    where the server has sent the email and is waiting for the second call.
    """

    token: str | None = None
    user: AdminUser | None = None
    challenge_issued: bool = False


def _mint(user: AdminUser, env: dict[str, str] | None) -> LoginResponse:
    token = issue_admin_token(user_id=user.id, email=user.email, role=user.role, env=env)
    return LoginResponse(token=token, user=user)


def perform_login(
    config: CertConfig,
    *,
    db_path: str | Path,
    kv: KVBackend,
    email_provider: EmailProvider,
    params: dict[str, Any],
    env: dict[str, str] | None = None,
    magic_link_builder=None,  # type: ignore[no-untyped-def]
) -> LoginResponse:
    """Dispatch to the configured auth mode. Raises :class:`LoginError` on failure."""
    mode = config.admin.auth_mode
    email = str(params.get("email", "")).strip().lower()

    if mode == "password":
        password = str(params.get("password", ""))
        if not email or not password:
            raise LoginError("email and password are required")
        user = verify_admin_password(db_path, email=email, password=password)
        if user is None:
            _LOGGER.info("admin login failed (password) for %s", email)
            raise LoginError("invalid credentials")
        return _mint(user, env)

    if mode == "otp_email":
        if not email:
            raise LoginError("email is required")
        user = get_admin_user(db_path, email=email)
        if user is None or not user.is_active:
            _LOGGER.info("admin login requested OTP for unknown/inactive %s", email)
            raise LoginError("invalid credentials")
        code = params.get("code")
        if code is None:
            issue_otp(kv, email_provider, email=email)
            return LoginResponse(challenge_issued=True)
        try:
            verify_otp(kv, email=email, code=str(code))
        except OTPError as e:
            _LOGGER.info("admin OTP verify failed for %s: %s", email, e)
            raise LoginError("invalid credentials") from e
        return _mint(user, env)

    if mode == "magic_link":
        token = params.get("token")
        if token is None:
            if not email:
                raise LoginError("email is required to request a magic link")
            user = get_admin_user(db_path, email=email)
            if user is None or not user.is_active:
                _LOGGER.info("admin magic-link requested for unknown/inactive %s", email)
                raise LoginError("invalid credentials")
            if magic_link_builder is None:
                raise LoginError("magic_link_builder is required when issuing a magic link")
            issue_magic_link(kv, email_provider, email=email, link_builder=magic_link_builder)
            return LoginResponse(challenge_issued=True)
        try:
            resolved_email = verify_magic_link(kv, str(token))
        except MagicLinkError as e:
            _LOGGER.info("admin magic-link verify failed: %s", e)
            raise LoginError("invalid credentials") from e
        user = get_admin_user(db_path, email=resolved_email)
        if user is None or not user.is_active:
            raise LoginError("invalid credentials")
        return _mint(user, env)

    raise LoginError(f"unknown admin.auth_mode: {mode!r}")
