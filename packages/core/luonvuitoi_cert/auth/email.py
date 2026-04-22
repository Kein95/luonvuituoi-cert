"""Email providers for OTP / magic-link delivery.

Two implementations ship:

- :class:`NullEmailProvider` — swallows messages into an in-process list.
  Tests and local dev use it so no real provider credentials are needed.
- :class:`ResendProvider` — wraps the Resend HTTP API.

The :class:`EmailProvider` protocol keeps handler code provider-agnostic so
dropping in SendGrid / SMTP is a 30-line module, not a refactor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import httpx


class EmailError(Exception):
    """Raised when a message can't be delivered."""


@dataclass(frozen=True, slots=True)
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str | None = None


@runtime_checkable
class EmailProvider(Protocol):
    def send(self, message: EmailMessage) -> None: ...


@dataclass(slots=True)
class NullEmailProvider:
    """Records messages in ``.sent`` instead of dispatching. Safe default."""

    sent: list[EmailMessage] = field(default_factory=list)

    def send(self, message: EmailMessage) -> None:
        if "@" not in message.to:
            raise EmailError(f"invalid recipient: {message.to!r}")
        self.sent.append(message)


class ResendProvider:
    """Thin wrapper over the Resend v1 send API. No retries — handlers decide."""

    ENDPOINT = "https://api.resend.com/emails"

    def __init__(self, api_key: str, *, from_address: str, timeout: float = 10.0) -> None:
        if not api_key:
            raise EmailError("RESEND_API_KEY must be set")
        if "@" not in from_address:
            raise EmailError(f"invalid from_address: {from_address!r}")
        self._api_key = api_key
        self._from = from_address
        self._client = httpx.Client(timeout=timeout)

    def send(self, message: EmailMessage) -> None:
        if "@" not in message.to:
            raise EmailError(f"invalid recipient: {message.to!r}")
        payload: dict[str, object] = {
            "from": self._from,
            "to": [message.to],
            "subject": message.subject,
            "text": message.text,
        }
        if message.html:
            payload["html"] = message.html
        try:
            resp = self._client.post(
                self.ENDPOINT,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise EmailError(f"Resend API error: {e}") from e

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ResendProvider:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
