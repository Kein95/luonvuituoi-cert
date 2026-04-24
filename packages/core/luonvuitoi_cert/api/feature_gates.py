"""Super-admin-controlled runtime gates for the public lookup + download surfaces.

Two independent booleans live in the KV so super-admins can flip them without
a redeploy:

- ``public_lookup_enabled`` — gates ``/api/search`` (student mode).
- ``public_download_enabled`` — gates ``/api/download`` (student mode).

Invariant enforced both on write and on read: download requires lookup. A
recipient who can't find their record cannot be handed a PDF either, so the
downstream gate refuses unconditionally when the upstream gate is off. Admin
mode bypasses both — operators still need to run the panel during a public
freeze (e.g. embargo period before results publish).

Defaults: both ON. A fresh deploy that never writes to KV behaves exactly
like the pre-gate codebase, so this module is additive.
"""

from __future__ import annotations

from dataclasses import dataclass

from luonvuitoi_cert.storage.kv.base import KVBackend

KV_LOOKUP_KEY = "feature:public_lookup_enabled"
KV_DOWNLOAD_KEY = "feature:public_download_enabled"


class FeatureDisabledError(Exception):
    """Raised when a gated public surface is called while its flag is off."""


@dataclass(frozen=True, slots=True)
class FeatureState:
    lookup_enabled: bool
    download_enabled: bool


def _read_flag(kv: KVBackend, key: str, *, default: bool) -> bool:
    raw = kv.get(key)
    if raw is None:
        return default
    return raw.strip() in {"1", "true", "yes", "on"}


def get_state(kv: KVBackend) -> FeatureState:
    """Return the current gate state, applying the download⇒lookup invariant.

    Any stored ``download=true`` is masked to ``false`` when ``lookup=false``
    so a caller can't observe an inconsistent pair even if the KV was seeded
    by hand.
    """
    lookup = _read_flag(kv, KV_LOOKUP_KEY, default=True)
    download = _read_flag(kv, KV_DOWNLOAD_KEY, default=True)
    return FeatureState(lookup_enabled=lookup, download_enabled=lookup and download)


def set_state(kv: KVBackend, *, lookup_enabled: bool, download_enabled: bool) -> FeatureState:
    """Persist a new gate state. Forces ``download=false`` when ``lookup=false``.

    The write is two separate KV operations — concurrent writers racing each
    other can't leave the pair in an invalid combination because :func:`get_state`
    re-applies the invariant on read.
    """
    effective_download = download_enabled and lookup_enabled
    kv.set(KV_LOOKUP_KEY, "1" if lookup_enabled else "0")
    kv.set(KV_DOWNLOAD_KEY, "1" if effective_download else "0")
    return FeatureState(lookup_enabled=lookup_enabled, download_enabled=effective_download)


def require_public_lookup(kv: KVBackend) -> None:
    """Raise :class:`FeatureDisabledError` when the public lookup gate is off."""
    if not get_state(kv).lookup_enabled:
        raise FeatureDisabledError("public lookup is currently disabled by the operator")


def require_public_download(kv: KVBackend) -> None:
    """Raise :class:`FeatureDisabledError` when the public download gate is off.

    The invariant means this also fires when lookup is off, even if the
    download flag was explicitly set to true at some point.
    """
    state = get_state(kv)
    if not state.lookup_enabled:
        raise FeatureDisabledError("public lookup is currently disabled by the operator")
    if not state.download_enabled:
        raise FeatureDisabledError("public certificate download is currently disabled by the operator")
