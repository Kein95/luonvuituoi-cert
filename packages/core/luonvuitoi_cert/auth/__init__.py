"""Admin authentication + authorization primitives.

Three login flavors share a common shape: the caller hands us a challenge
payload, we verify it, and we emit a short-lived JWT that later requests
present to the admin handlers. The JWT embeds ``sub`` (admin user id),
``role``, and a ``jti`` (single-use marker the activity log tracks).

The login flavor is picked by ``config.admin.auth_mode``:

- ``password`` — classic email + password bcrypt-style check
- ``otp_email`` — one-time 6-digit code delivered by email
- ``magic_link`` — one-time URL token delivered by email

All three mint identical JWTs on success, so admin handlers stay auth-mode
agnostic.
"""

from luonvuitoi_cert.auth.activity_log import (
    ActivityLog,
    ActivityLogEntry,
    log_admin_action,
)
from luonvuitoi_cert.auth.admin_db import (
    AdminUser,
    AdminUserError,
    Role,
    create_admin_user,
    delete_admin_user,
    ensure_admin_schema,
    get_admin_user,
    list_admin_users,
    update_admin_password,
)
from luonvuitoi_cert.auth.email import EmailError, NullEmailProvider, ResendProvider
from luonvuitoi_cert.auth.login import LoginError, LoginResponse, perform_login
from luonvuitoi_cert.auth.magic_link import issue_magic_link, verify_magic_link
from luonvuitoi_cert.auth.otp import issue_otp, verify_otp
from luonvuitoi_cert.auth.passwords import hash_password, verify_password
from luonvuitoi_cert.auth.tokens import (
    AdminToken,
    TokenError,
    issue_admin_token,
    verify_admin_token,
)

__all__ = [
    "ActivityLog",
    "ActivityLogEntry",
    "AdminToken",
    "AdminUser",
    "AdminUserError",
    "EmailError",
    "LoginError",
    "LoginResponse",
    "NullEmailProvider",
    "ResendProvider",
    "Role",
    "TokenError",
    "create_admin_user",
    "delete_admin_user",
    "ensure_admin_schema",
    "get_admin_user",
    "hash_password",
    "issue_admin_token",
    "issue_magic_link",
    "issue_otp",
    "list_admin_users",
    "log_admin_action",
    "perform_login",
    "update_admin_password",
    "verify_admin_token",
    "verify_magic_link",
    "verify_otp",
    "verify_password",
]
