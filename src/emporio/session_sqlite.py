"""SQLite adapter for bounded, principal-isolated sessions."""

from __future__ import annotations

import hashlib
import hmac
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from .config import principal_binding_secret
from .order import AuthorizedPrincipal
from .session import (
    SessionAccessError,
    SessionContext,
    SessionExpiredError,
    SessionId,
    SessionLimits,
    SessionMessage,
    SessionStorageError,
    SessionValidationError,
)


class SQLiteSessionRepository:
    def __init__(
        self,
        connection: sqlite3.Connection,
        limits: SessionLimits | None = None,
        *,
        principal_secret: bytes | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._connection = connection
        self._limits = limits or SessionLimits()
        self._principal_secret = principal_secret or principal_binding_secret()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._ensure_schema()

    @classmethod
    def connect(
        cls,
        path: str | Path,
        limits: SessionLimits | None = None,
        *,
        principal_secret: bytes | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> SQLiteSessionRepository:
        database = Path(path)
        try:
            database.parent.mkdir(parents=True, exist_ok=True)
            return cls(
                sqlite3.connect(str(database), timeout=5.0),
                limits,
                principal_secret=principal_secret,
                clock=clock,
            )
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise SessionStorageError("session storage is unavailable") from exc

    def set_clock(self, clock: Callable[[], datetime]) -> None:
        """Allow the application service's deterministic clock to govern writes."""
        self._clock = clock

    def purge_expired(self, now: datetime) -> None:
        if now.tzinfo is None:
            raise SessionStorageError("purge time must include a timezone")
        try:
            with self._connection:
                rows = self._connection.execute(
                    "SELECT session_id, expires_at FROM sessions"
                ).fetchall()
                expired_ids = [
                    row["session_id"]
                    for row in rows
                    if now >= self._timestamp(row["expires_at"], "expiry")
                ]
                for session_id in expired_ids:
                    self._connection.execute(
                        "DELETE FROM sessions WHERE session_id = ?", (session_id,)
                    )
        except SessionStorageError:
            raise
        except sqlite3.Error as exc:
            raise SessionStorageError("session storage is unavailable") from exc

    def invalidate(self, session_id: SessionId) -> None:
        """Quarantine a session whose contents could not be safely recovered."""
        try:
            with self._connection:
                self._connection.execute(
                    "DELETE FROM sessions WHERE session_id = ?", (str(session_id),)
                )
        except sqlite3.Error as exc:
            raise SessionStorageError("session storage is unavailable") from exc

    def _ensure_schema(self) -> None:
        try:
            self._connection.execute("BEGIN")
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    principal_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS session_messages (
                    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, sequence)
                )"""
            )
            self._connection.commit()
        except sqlite3.Error as exc:
            self._connection.rollback()
            raise SessionStorageError("session storage is unavailable") from exc

    def _principal_key(self, principal: AuthorizedPrincipal | None) -> str:
        if principal is not None and not isinstance(principal, AuthorizedPrincipal):
            raise SessionAccessError("principal must be established by the server")
        identity = "anonymous" if principal is None else f"customer:{principal.customer_id}"
        return hmac.new(
            self._principal_secret, identity.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    @staticmethod
    def _timestamp(value: str, label: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise SessionStorageError(f"session storage contains an invalid {label}") from exc
        if parsed.tzinfo is None:
            raise SessionStorageError(f"session storage contains a timezone-less {label}")
        return parsed

    def create(
        self, session_id: SessionId, principal: AuthorizedPrincipal | None, expires_at: datetime
    ) -> SessionContext:
        if expires_at.tzinfo is None:
            raise SessionStorageError("session expiry must include a timezone")
        now = expires_at - self._limits.ttl
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO sessions(session_id, principal_key, created_at, expires_at) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        str(session_id),
                        self._principal_key(principal),
                        now.isoformat(),
                        expires_at.isoformat(),
                    ),
                )
        except sqlite3.Error as exc:
            raise SessionStorageError("session could not be created") from exc
        return SessionContext(session_id, (), expires_at)

    def read(
        self, session_id: SessionId, principal: AuthorizedPrincipal | None, now: datetime
    ) -> SessionContext:
        try:
            row = self._authorized_row(session_id, principal)
            expires_at = self._timestamp(row["expires_at"], "expiry")
            if now >= expires_at:
                self._delete_session(session_id)
                raise SessionExpiredError("session expired")
            rows = self._connection.execute(
                "SELECT role, content, created_at FROM session_messages "
                "WHERE session_id = ? ORDER BY sequence",
                (str(session_id),),
            ).fetchall()
            messages = tuple(
                SessionMessage.create(
                    item["role"],
                    item["content"],
                    self._limits,
                    self._timestamp(item["created_at"], "message timestamp"),
                )
                for item in rows
            )
            return SessionContext(session_id, messages, expires_at)
        except (SessionAccessError, SessionExpiredError, SessionStorageError):
            raise
        except (sqlite3.Error, TypeError, SessionValidationError) as exc:
            raise SessionStorageError("session storage contains unusable data") from exc

    def get(
        self, session_id: SessionId, principal: AuthorizedPrincipal | None, now: datetime
    ) -> SessionContext:
        return self.read(session_id, principal, now)

    def expire(
        self, session_id: SessionId, principal: AuthorizedPrincipal | None, now: datetime
    ) -> None:
        try:
            row = self._authorized_row(session_id, principal)
            expires_at = self._timestamp(row["expires_at"], "expiry")
            if now < expires_at:
                raise SessionExpiredError("session is still active")
            self._delete_session(session_id)
        except (SessionAccessError, SessionExpiredError, SessionStorageError):
            raise
        except sqlite3.Error as exc:
            raise SessionStorageError("session storage is unavailable") from exc

    def append(
        self,
        session_id: SessionId,
        principal: AuthorizedPrincipal | None,
        message: SessionMessage,
        now: datetime,
    ) -> SessionContext:
        validated = SessionMessage.create(
            message.role.value, message.content, self._limits, message.created_at
        )
        for attempt in range(4):
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                row = self._authorized_row(session_id, principal)
                expires_at = self._timestamp(row["expires_at"], "expiry")
                effective_now = self._clock()
                if effective_now.tzinfo is None:
                    raise SessionStorageError("write time must include a timezone")
                if effective_now >= expires_at:
                    self._delete_session(session_id, in_transaction=True)
                    self._connection.commit()
                    raise SessionExpiredError("session expired")
                next_sequence = self._connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM session_messages "
                    "WHERE session_id = ?",
                    (str(session_id),),
                ).fetchone()[0]
                self._connection.execute(
                    "INSERT INTO session_messages(session_id, sequence, role, content, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        str(session_id),
                        next_sequence,
                        validated.role.value,
                        validated.content,
                        validated.created_at.isoformat(),
                    ),
                )
                self._connection.execute(
                    "DELETE FROM session_messages WHERE session_id = ? AND sequence <= "
                    "(SELECT COALESCE(MAX(sequence), 0) - ? FROM session_messages "
                    "WHERE session_id = ?)",
                    (str(session_id), self._limits.max_messages, str(session_id)),
                )
                rows = self._connection.execute(
                    "SELECT role, content, created_at FROM session_messages "
                    "WHERE session_id = ? ORDER BY sequence",
                    (str(session_id),),
                ).fetchall()
                context = SessionContext(
                    session_id,
                    tuple(
                        SessionMessage.create(
                            item["role"],
                            item["content"],
                            self._limits,
                            self._timestamp(item["created_at"], "message timestamp"),
                        )
                        for item in rows
                    ),
                    expires_at,
                )
                self._connection.commit()
                return context
            except (SessionAccessError, SessionExpiredError, SessionStorageError):
                if self._connection.in_transaction:
                    self._connection.rollback()
                raise
            except SessionValidationError as exc:
                if self._connection.in_transaction:
                    self._connection.rollback()
                raise SessionStorageError("session storage contains unusable data") from exc
            except sqlite3.OperationalError as exc:
                if self._connection.in_transaction:
                    self._connection.rollback()
                if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                    raise SessionStorageError("session message could not be stored") from exc
                if attempt == 3:
                    raise SessionStorageError("session message could not be stored") from exc
                time.sleep(0.02 * (attempt + 1))
            except sqlite3.Error as exc:
                if self._connection.in_transaction:
                    self._connection.rollback()
                raise SessionStorageError("session message could not be stored") from exc
        raise SessionStorageError("session message could not be stored")

    def _authorized_row(
        self, session_id: SessionId, principal: AuthorizedPrincipal | None
    ) -> sqlite3.Row:
        row = self._connection.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (str(session_id),)
        ).fetchone()
        if row is None or not hmac.compare_digest(
            row["principal_key"], self._principal_key(principal)
        ):
            raise SessionAccessError("session is not accessible")
        return row

    def _delete_session(self, session_id: SessionId, *, in_transaction: bool = False) -> None:
        if in_transaction:
            self._connection.execute(
                "DELETE FROM sessions WHERE session_id = ?", (str(session_id),)
            )
        else:
            with self._connection:
                self._connection.execute(
                    "DELETE FROM sessions WHERE session_id = ?", (str(session_id),)
                )
