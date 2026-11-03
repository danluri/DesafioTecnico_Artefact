"""Bounded, normalized conversation-session domain types."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from uuid import UUID, uuid4


class SessionError(Exception):
    """Base error for session operations."""


class SessionValidationError(SessionError):
    """A session value or message is not safe to store."""


class UnsupportedRoleError(SessionValidationError):
    """The message role is not part of the normalized application contract."""


class SessionExpiredError(SessionError):
    """The session is no longer eligible for private context."""


class SessionAccessError(SessionError):
    """The session is missing or bound to another principal."""


class SessionStorageError(SessionError):
    """Session storage could not safely complete an operation."""


class PersistenceState(StrEnum):
    PERSISTED = "persisted"
    RECOVERABLE_UNPERSISTED = "recoverable_unpersisted"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class SessionId:
    """Opaque UUID-backed identifier; it is never derived from a principal."""

    value: UUID

    @classmethod
    def new(cls) -> SessionId:
        return cls(uuid4())

    @classmethod
    def parse(cls, value: str) -> SessionId:
        try:
            parsed = UUID(value)
        except (AttributeError, ValueError, TypeError) as exc:
            raise SessionValidationError("invalid session id") from exc
        return cls(parsed)

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class SessionLimits:
    max_messages: int = 20
    max_message_chars: int = 8_000
    ttl: timedelta = timedelta(hours=24)

    def __post_init__(self) -> None:
        if self.max_messages < 1 or self.max_message_chars < 1 or self.ttl <= timedelta(0):
            raise ValueError("session limits must be positive")


def normalize_message_text(content: str, limits: SessionLimits) -> str:
    if not isinstance(content, str):
        raise SessionValidationError("message content must be text")
    normalized = unicodedata.normalize("NFC", content)
    safe_chars: list[str] = []
    for char in normalized:
        if unicodedata.category(char) == "Cc":
            if char in "\t\n\r":
                safe_chars.append(" ")
                continue
            raise SessionValidationError("message content contains unsafe control characters")
        safe_chars.append(char)
    normalized = "".join(safe_chars).strip()
    if not normalized:
        raise SessionValidationError("message content cannot be empty")
    if len(normalized) > limits.max_message_chars:
        raise SessionValidationError("message content exceeds the configured bound")
    return normalized


@dataclass(frozen=True, slots=True)
class SessionMessage:
    role: MessageRole
    content: str
    created_at: datetime

    @classmethod
    def create(
        cls, role: MessageRole | str, content: str, limits: SessionLimits, created_at: datetime
    ) -> SessionMessage:
        try:
            normalized_role = MessageRole(role)
        except (TypeError, ValueError) as exc:
            raise UnsupportedRoleError("unsupported message role") from exc
        if created_at.tzinfo is None:
            raise SessionValidationError("message timestamp must include a timezone")
        return cls(normalized_role, normalize_message_text(content, limits), created_at)


@dataclass(frozen=True, slots=True)
class SessionContext:
    session_id: SessionId
    messages: tuple[SessionMessage, ...]
    expires_at: datetime
    persistence: PersistenceState = PersistenceState.PERSISTED


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

