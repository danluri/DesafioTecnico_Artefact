"""Optional WhatsApp webhook normalization and ConversationService routing seam."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol


class WhatsAppVerificationError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class WhatsAppConfig:
    enabled: bool = False
    verify_token: str | None = None
    access_token: str | None = None
    phone_number_id: str | None = None
    api_base_url: str | None = None
    app_secret: str | None = None
    idempotency_db_path: str | None = None

    @classmethod
    def from_env(cls) -> "WhatsAppConfig":
        config = cls(
            os.getenv("EMPORIO_WHATSAPP_ENABLED", "false").lower() in {"1", "true", "yes", "on"},
            os.getenv("EMPORIO_WHATSAPP_VERIFY_TOKEN") or None,
            os.getenv("EMPORIO_WHATSAPP_ACCESS_TOKEN") or None,
            os.getenv("EMPORIO_WHATSAPP_PHONE_NUMBER_ID") or None,
            os.getenv("EMPORIO_WHATSAPP_API_BASE_URL") or None,
            os.getenv("EMPORIO_WHATSAPP_APP_SECRET") or None,
            os.getenv("EMPORIO_WHATSAPP_IDEMPOTENCY_DB") or None,
        )
        if config.enabled and (not config.verify_token or not config.app_secret):
            raise ValueError("enabled WhatsApp requires verify token and app secret")
        return config


@dataclass(frozen=True, slots=True)
class InboundWhatsAppMessage:
    message_id: str
    sender: str
    text: str
    received_at: datetime


@dataclass(frozen=True, slots=True)
class WhatsAppWebhookResult:
    accepted: bool
    duplicate: bool = False
    message: InboundWhatsAppMessage | None = None
    response: Any = None


class ConversationPort(Protocol):
    def respond(self, text: str, **kwargs: Any) -> Any: ...


class WhatsAppWebhookAdapter:
    def __init__(self, config: WhatsAppConfig | None = None) -> None:
        self.config = config or WhatsAppConfig.from_env()
        self._seen: set[str] = set()
        self._idempotency = (
            _SQLiteIdempotency(self.config.idempotency_db_path)
            if self.config.idempotency_db_path
            else None
        )

    def verify_get(self, mode: str, verify_token: str, challenge: str) -> str:
        if mode != "subscribe" or not self.config.verify_token or not hmac.compare_digest(
            verify_token, self.config.verify_token
        ):
            raise WhatsAppVerificationError("invalid webhook verification")
        return challenge

    def handle(
        self,
        raw_body: bytes,
        conversation: ConversationPort,
        *,
        signature: str | None = None,
    ) -> WhatsAppWebhookResult:
        if not self.config.enabled:
            raise WhatsAppVerificationError("WhatsApp is disabled")
        secret = self.config.app_secret
        if not secret or not signature:
            raise WhatsAppVerificationError("missing webhook signature")
        if not isinstance(raw_body, bytes):
            raise WhatsAppVerificationError("raw webhook body is required")
        expected = "sha256=" + hmac.new(
            secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise WhatsAppVerificationError("invalid webhook signature")
        try:
            payload = json.loads(raw_body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise WhatsAppVerificationError("invalid webhook JSON") from None
        message = _normalize(payload)
        if self._idempotency:
            first_delivery = self._idempotency.claim(message.message_id)
        else:
            with _seen_lock:
                first_delivery = message.message_id not in self._seen
                if first_delivery:
                    self._seen.add(message.message_id)
        if not first_delivery:
            return WhatsAppWebhookResult(True, True, message)
        response = conversation.respond(message.text)
        return WhatsAppWebhookResult(True, False, message, response)


def _normalize(payload: Any) -> InboundWhatsAppMessage:
    try:
        entries = payload["entry"]
        values = [change["value"] for entry in entries for change in entry["changes"]]
        messages = [message for value in values for message in value.get("messages", [])]
        if len(entries) != 1 or len(values) != 1 or len(messages) != 1:
            raise WhatsAppVerificationError("batch webhook is not supported")
        value = messages[0]
        message_id, sender = value["id"], value["from"]
        text = value["text"]["body"]
    except (KeyError, IndexError, TypeError):
        raise WhatsAppVerificationError("invalid webhook shape") from None
    if not all(isinstance(item, str) and item.strip() for item in (message_id, sender, text)):
        raise WhatsAppVerificationError("invalid normalized message")
    return InboundWhatsAppMessage(message_id, sender, text.strip(), datetime.now(timezone.utc))


class _SQLiteIdempotency:
    def __init__(self, path: str) -> None:
        self._path = path
        self._local = threading.local()
        connection = self._connection
        connection.execute(
            "CREATE TABLE IF NOT EXISTS whatsapp_events (message_id TEXT PRIMARY KEY)"
        )
        connection.commit()

    @property
    def _connection(self) -> sqlite3.Connection:
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = sqlite3.connect(self._path, timeout=5.0)
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA journal_mode = WAL")
            self._local.connection = connection
        return connection

    def claim(self, message_id: str) -> bool:
        cursor = self._connection.execute(
            "INSERT OR IGNORE INTO whatsapp_events(message_id) VALUES (?)", (message_id,)
        )
        self._connection.commit()
        return cursor.rowcount == 1


_seen_lock = threading.Lock()
