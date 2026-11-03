"""Port for isolated session persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .order import AuthorizedPrincipal
from .session import SessionContext, SessionId, SessionMessage


class SessionRepository(Protocol):
    def purge_expired(self, now: datetime) -> None: ...

    def invalidate(self, session_id: SessionId) -> None: ...

    def create(
        self, session_id: SessionId, principal: AuthorizedPrincipal | None, expires_at: datetime
    ) -> SessionContext: ...

    def read(
        self, session_id: SessionId, principal: AuthorizedPrincipal | None, now: datetime
    ) -> SessionContext: ...

    def append(
        self,
        session_id: SessionId,
        principal: AuthorizedPrincipal | None,
        message: SessionMessage,
        now: datetime,
    ) -> SessionContext: ...

    def expire(
        self, session_id: SessionId, principal: AuthorizedPrincipal | None, now: datetime
    ) -> None: ...

