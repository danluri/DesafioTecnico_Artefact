"""Application service owning session lifecycle and fail-closed behavior."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from .order import AuthorizedPrincipal
from .session import (
    PersistenceState,
    SessionAccessError,
    SessionContext,
    SessionExpiredError,
    SessionId,
    SessionLimits,
    SessionMessage,
    SessionStorageError,
    utc_now,
)
from .session_repository import SessionRepository


class SessionService:
    def __init__(
        self,
        repository: SessionRepository,
        *,
        limits: SessionLimits | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._limits = limits or SessionLimits()
        self._clock = clock
        set_clock = getattr(repository, "set_clock", None)
        if callable(set_clock):
            set_clock(clock)

    def create_session(self, principal: AuthorizedPrincipal | None = None) -> SessionContext:
        now = self._clock()
        session_id = SessionId.new()
        expires_at = now + self._limits.ttl
        try:
            return self._repository.create(session_id, principal, expires_at)
        except SessionStorageError:
            return SessionContext(
                session_id, (), expires_at, PersistenceState.RECOVERABLE_UNPERSISTED
            )

    def get_context(
        self, session_id: SessionId | str, principal: AuthorizedPrincipal | None = None
    ) -> SessionContext:
        parsed = self._session_id(session_id)
        try:
            return self._repository.read(parsed, principal, self._clock())
        except SessionExpiredError:
            return self.create_session(principal)
        except SessionStorageError:
            self._invalidate(parsed)
            return self.create_session(principal)

    def append_message(
        self,
        session_id: SessionId | str,
        role: str,
        content: str,
        principal: AuthorizedPrincipal | None = None,
    ) -> SessionContext:
        parsed = self._session_id(session_id)
        now = self._clock()
        message = SessionMessage.create(role, content, self._limits, now)
        try:
            return self._repository.append(parsed, principal, message, now)
        except SessionExpiredError:
            return self.create_session(principal)
        except SessionStorageError:
            self._invalidate(parsed)
            return self.create_session(principal)
        except SessionAccessError:
            raise

    def _session_id(self, value: SessionId | str) -> SessionId:
        if isinstance(value, SessionId):
            return value
        return SessionId.parse(value)

    def _invalidate(self, session_id: SessionId) -> None:
        invalidate = getattr(self._repository, "invalidate", None)
        if not callable(invalidate):
            return
        try:
            invalidate(session_id)
        except SessionStorageError:
            # The fresh context remains explicitly unpersisted if storage is still down.
            return

