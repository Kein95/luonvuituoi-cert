"""Pure-function request handlers for search, download, CAPTCHA, and admin.

Every public entry point takes an input dict and the runtime dependencies
(config, DB path, KV backend, project root) and returns a typed response.
This lets the same logic run under Vercel's ``BaseHTTPRequestHandler`` in
production and under Flask in the local dev server — both wrap these pure
functions with transport-specific glue.
"""

from luonvuitoi_cert.api.admin_list import (
    AdminListError,
    AdminListResponse,
    AdminListRow,
    admin_list_students,
)
from luonvuitoi_cert.api.captcha import (
    CaptchaChallenge,
    CaptchaError,
    issue_challenge,
    verify_challenge,
)
from luonvuitoi_cert.api.download import DownloadResponse, download_certificate
from luonvuitoi_cert.api.rate_limiter import RateLimitError, check_rate_limit
from luonvuitoi_cert.api.search import (
    SearchError,
    SearchResult,
    search_student,
)
from luonvuitoi_cert.api.security import (
    DEFAULT_ALLOWED_ORIGINS,
    SecurityError,
    clean_sbd,
    sanitize_filename,
    validate_request_size,
    validate_sbd,
)
from luonvuitoi_cert.api.shipment import (
    ShipmentHandlerError,
    ShipmentLookupResponse,
    lookup_shipment,
    upsert_shipment_record,
)
from luonvuitoi_cert.api.verify import VerifyError, VerifyResponse, verify_qr

__all__ = [
    "AdminListError",
    "AdminListResponse",
    "AdminListRow",
    "CaptchaChallenge",
    "CaptchaError",
    "DEFAULT_ALLOWED_ORIGINS",
    "DownloadResponse",
    "RateLimitError",
    "SearchError",
    "SearchResult",
    "SecurityError",
    "ShipmentHandlerError",
    "ShipmentLookupResponse",
    "VerifyError",
    "VerifyResponse",
    "admin_list_students",
    "check_rate_limit",
    "clean_sbd",
    "download_certificate",
    "issue_challenge",
    "lookup_shipment",
    "sanitize_filename",
    "search_student",
    "upsert_shipment_record",
    "validate_request_size",
    "validate_sbd",
    "verify_challenge",
    "verify_qr",
]
