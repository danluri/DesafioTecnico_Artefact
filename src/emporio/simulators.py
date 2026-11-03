"""Deterministic local simulators for optional provider integrations."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .correios import CorreiosUnavailable, TrackingResult
from .whatsapp import WhatsAppConfig, WhatsAppWebhookAdapter, WhatsAppWebhookResult

MOCK_WHATSAPP_APP_SECRET = "local-whatsapp-simulator-secret"
MOCK_WHATSAPP_VERIFY_TOKEN = "local-whatsapp-simulator-verify"


@dataclass(frozen=True, slots=True)
class MockCorreiosTracking:
    """Return deterministic tracking data without calling Correios."""

    status: str = "Objeto em tr\u00e2nsito"
    observed_at: datetime = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
    message: str = "Resultado sintetico para desenvolvimento local."

    def track(self, tracking_code: str) -> TrackingResult:
        code = tracking_code.strip() if isinstance(tracking_code, str) else ""
        if not code or len(code) > 13 or not code.isalnum():
            raise CorreiosUnavailable("invalid tracking code")
        return TrackingResult(
            status=self.status,
            observed_at=self.observed_at,
            source="Mock Correios",
            provenance="local simulator; no Correios request was made",
            message=self.message,
        )


def mock_whatsapp_config(*, idempotency_db_path: str | None = None) -> WhatsAppConfig:
    """Build an enabled local config with synthetic secrets, never provider credentials."""
    return WhatsAppConfig(
        enabled=True,
        verify_token=MOCK_WHATSAPP_VERIFY_TOKEN,
        app_secret=MOCK_WHATSAPP_APP_SECRET,
        idempotency_db_path=idempotency_db_path,
    )


def mock_whatsapp_payload(
    *, message_id: str = "mock-wamid-1", sender: str = "5511999999999", text: str = "oi"
) -> dict[str, Any]:
    """Generate one WhatsApp-shaped inbound message for local tests."""
    return {
        "entry": [{
            "changes": [{
                "value": {"messages": [{"id": message_id, "from": sender, "text": {"body": text}}]}
            }]
        }]
    }


class MockWhatsAppChannel:
    """Deliver generated messages through the real webhook adapter locally."""

    def __init__(self, adapter: WhatsAppWebhookAdapter) -> None:
        if (
            adapter.config.app_secret != MOCK_WHATSAPP_APP_SECRET
            or adapter.config.access_token
            or adapter.config.phone_number_id
            or adapter.config.api_base_url
        ):
            raise ValueError("MockWhatsAppChannel requires mock-only WhatsApp configuration")
        self.adapter = adapter
        self.secret = adapter.config.app_secret or ""

    def deliver(
        self,
        conversation: Any,
        *,
        message_id: str = "mock-wamid-1",
        sender: str = "5511999999999",
        text: str = "oi",
    ) -> WhatsAppWebhookResult:
        fields = (message_id, sender, text)
        if not all(isinstance(value, str) and value.strip() for value in fields):
            raise ValueError("mock WhatsApp message fields must be non-empty strings")
        raw_body = json.dumps(
            mock_whatsapp_payload(message_id=message_id, sender=sender, text=text),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        signature = "sha256=" + hmac.new(
            self.secret.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
        return self.adapter.handle(raw_body, conversation, signature=signature)
