"""REST-protocol Redis client for Upstash and Vercel KV.

Both vendors expose the same HTTP command surface: POST a JSON array of
command args (``["GET", "mykey"]``) to the base URL with a Bearer token.
Vercel KV is built on Upstash under the hood, so one adapter handles both —
the only thing that differs is which env var pair we read at construction.
"""

from __future__ import annotations

from typing import Any

import httpx

from luonvuitoi_cert.storage.kv.base import KVError

DEFAULT_TIMEOUT = 5.0


class RestKV:
    """Talks to Upstash / Vercel-KV over HTTPS.

    Use :func:`open_kv` or the classmethods to construct from env vars.
    """

    def __init__(self, base_url: str, token: str, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        if not base_url or not token:
            raise KVError("RestKV requires both base_url and token")
        self._base = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )

    @classmethod
    def from_upstash_env(cls, env: dict[str, str]) -> "RestKV":
        url = env.get("UPSTASH_REDIS_REST_URL", "")
        token = env.get("UPSTASH_REDIS_REST_TOKEN", "")
        if not url or not token:
            raise KVError("UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN must be set")
        return cls(url, token)

    @classmethod
    def from_vercel_env(cls, env: dict[str, str]) -> "RestKV":
        url = env.get("KV_REST_API_URL", "")
        token = env.get("KV_REST_API_TOKEN", "")
        if not url or not token:
            raise KVError("KV_REST_API_URL and KV_REST_API_TOKEN must be set")
        return cls(url, token)

    # ── Transport ──────────────────────────────────────────────────
    def _command(self, *args: Any) -> Any:
        try:
            resp = self._client.post("/", json=[str(a) for a in args])
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise KVError(f"RestKV transport error: {e}") from e
        body = resp.json()
        if isinstance(body, dict) and "error" in body:
            raise KVError(f"RestKV command error: {body['error']}")
        return body.get("result") if isinstance(body, dict) else body

    # ── KVBackend surface ──────────────────────────────────────────
    def get(self, key: str) -> str | None:
        result = self._command("GET", key)
        return None if result is None else str(result)

    def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        if ttl_seconds and ttl_seconds > 0:
            self._command("SET", key, value, "EX", ttl_seconds)
        else:
            self._command("SET", key, value)

    def delete(self, key: str) -> None:
        self._command("DEL", key)

    def exists(self, key: str) -> bool:
        return bool(self._command("EXISTS", key))

    def scan_prefix(self, prefix: str, *, limit: int = 100) -> list[str]:
        # Uses SCAN which Upstash/Vercel KV both expose. Cursor-paginates until limit reached.
        collected: list[str] = []
        cursor = "0"
        while True:
            result = self._command("SCAN", cursor, "MATCH", f"{prefix}*", "COUNT", 100)
            if not isinstance(result, list) or len(result) != 2:
                break
            cursor, batch = str(result[0]), result[1] or []
            for key in batch:
                collected.append(str(key))
                if len(collected) >= limit:
                    return collected
            if cursor == "0":
                break
        return collected

    def close(self) -> None:
        self._client.close()
