from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from emporio.config import DEFAULT_DB_PATH, database_path, principal_binding_secret
from emporio.order import AuthorizedPrincipal
from emporio.session import (
    MessageRole,
    PersistenceState,
    SessionAccessError,
    SessionExpiredError,
    SessionLimits,
    SessionStorageError,
    SessionValidationError,
)
from emporio.session_service import SessionService
from emporio.session_sqlite import SQLiteSessionRepository


class FakeClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: int) -> None:
        self.value += timedelta(**kwargs)


@pytest.fixture
def service(tmp_path: Path) -> tuple[SessionService, FakeClock]:
    clock = FakeClock()
    limits = SessionLimits(max_messages=2, max_message_chars=10, ttl=timedelta(hours=1))
    repository = SQLiteSessionRepository.connect(tmp_path / "nested" / "sessions.db", limits)
    return SessionService(repository, limits=limits, clock=clock), clock


def test_continuity_is_bounded_and_ordered(service: tuple[SessionService, FakeClock]) -> None:
    app, _ = service
    principal = AuthorizedPrincipal(1)
    context = app.create_session(principal)
    app.append_message(context.session_id, "user", "first", principal)
    app.append_message(context.session_id, "assistant", "second", principal)
    current = app.append_message(context.session_id, "user", "third", principal)
    assert [message.content for message in current.messages] == ["second", "third"]
    assert [message.role for message in current.messages] == [
        MessageRole.ASSISTANT, MessageRole.USER
    ]


def test_sessions_are_isolated_and_principal_bound(
    service: tuple[SessionService, FakeClock]
) -> None:
    app, _ = service
    principal = AuthorizedPrincipal(1)
    first = app.create_session(principal)
    second = app.create_session(principal)
    app.append_message(first.session_id, "user", "private", principal)
    assert app.get_context(second.session_id, principal).messages == ()
    with pytest.raises(SessionAccessError):
        app.get_context(first.session_id, AuthorizedPrincipal(2))
    with pytest.raises(SessionAccessError):
        app.append_message(first.session_id, "user", "wrong", AuthorizedPrincipal(2))


def test_expiry_returns_fresh_empty_context(service: tuple[SessionService, FakeClock]) -> None:
    app, clock = service
    principal = AuthorizedPrincipal(1)
    original = app.create_session(principal)
    app.append_message(original.session_id, "user", "private", principal)
    clock.advance(hours=2)
    fresh = app.get_context(original.session_id, principal)
    assert fresh.session_id != original.session_id
    assert fresh.messages == ()
    assert repository_row_count(app, original.session_id) == 0


@pytest.mark.parametrize(
    "role,content",
    [("tool", "valid"), ("user", ""), ("user", "bad\x00text"), ("user", "12345678901")],
)
def test_invalid_message_does_not_mutate(
    service: tuple[SessionService, FakeClock], role: str, content: str
) -> None:
    app, _ = service
    principal = AuthorizedPrincipal(1)
    context = app.create_session(principal)
    with pytest.raises(SessionValidationError):
        app.append_message(context.session_id, role, content, principal)
    assert app.get_context(context.session_id, principal).messages == ()


def test_storage_failure_fails_closed() -> None:
    class BrokenRepository:
        def create(self, *args: object) -> object:
            raise SessionStorageError("broken")

        def read(self, *args: object) -> object:
            raise SessionStorageError("broken")

        def append(self, *args: object) -> object:
            raise SessionStorageError("broken")

    app = SessionService(BrokenRepository())
    principal = AuthorizedPrincipal(1)
    context = app.create_session(principal)
    assert context.messages == ()


def test_malformed_stored_message_fails_closed(tmp_path: Path) -> None:
    clock = FakeClock()
    repository = SQLiteSessionRepository.connect(tmp_path / "sessions.db")
    app = SessionService(repository, clock=clock)
    principal = AuthorizedPrincipal(1)
    context = app.create_session(principal)
    repository._connection.execute(
        "INSERT INTO session_messages(session_id, sequence, role, content, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(context.session_id), 1, "user", "x" * 9000, clock().isoformat()),
    )
    repository._connection.commit()
    fresh = app.get_context(context.session_id, principal)
    assert fresh.session_id != context.session_id
    assert fresh.messages == ()


def test_database_path_configuration_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("EMPORIO_DB_PATH", str(tmp_path / "docker" / "emporio.db"))
    assert database_path() == tmp_path / "docker" / "emporio.db"
    assert database_path(None).parent == tmp_path / "docker"
    monkeypatch.delenv("EMPORIO_DB_PATH")
    assert database_path() == DEFAULT_DB_PATH


def repository_row_count(app: SessionService, session_id: object) -> int:
    repository = app._repository
    return repository._connection.execute(
        "SELECT COUNT(*) FROM sessions WHERE session_id = ?", (str(session_id),)
    ).fetchone()[0]


def test_storage_failure_is_explicitly_unpersisted() -> None:
    class BrokenRepository:
        def create(self, *args: object) -> object:
            raise SessionStorageError("broken")

        def read(self, *args: object) -> object:
            raise SessionStorageError("broken")

        def append(self, *args: object) -> object:
            raise SessionStorageError("broken")

    context = SessionService(BrokenRepository()).create_session(AuthorizedPrincipal(1))
    assert context.persistence is PersistenceState.RECOVERABLE_UNPERSISTED


def test_storage_failure_preserves_message_for_current_request() -> None:
    class BrokenRepository:
        def create(self, *args: object) -> object:
            raise SessionStorageError("broken")

        def append(self, *args: object) -> object:
            raise SessionStorageError("broken")

    service = SessionService(BrokenRepository())
    context = service.create_session()
    recovered = service.append_message(context.session_id, "user", "pergunta local")

    assert recovered.persistence is PersistenceState.RECOVERABLE_UNPERSISTED
    assert [message.content for message in recovered.messages] == ["pergunta local"]


def test_storage_failure_invalidates_old_private_context(tmp_path: Path) -> None:
    clock = FakeClock()
    repository = SQLiteSessionRepository.connect(tmp_path / "quarantine.db")
    app = SessionService(repository, clock=clock)
    principal = AuthorizedPrincipal(1)
    original = app.create_session(principal)
    app.append_message(original.session_id, "user", "private", principal)
    repository._connection.execute(
        "UPDATE session_messages SET content = ? WHERE session_id = ?",
        ("x" * 9000, str(original.session_id)),
    )
    repository._connection.commit()

    fresh = app.get_context(original.session_id, principal)

    assert fresh.session_id != original.session_id
    assert repository._connection.execute(
        "SELECT COUNT(*) FROM sessions WHERE session_id = ?", (str(original.session_id),)
    ).fetchone()[0] == 0


def test_purge_expired_removes_untouched_sessions(tmp_path: Path) -> None:
    clock = FakeClock()
    limits = SessionLimits(ttl=timedelta(hours=1))
    repository = SQLiteSessionRepository.connect(tmp_path / "purge.db", limits)
    app = SessionService(repository, limits=limits, clock=clock)
    principal = AuthorizedPrincipal(1)
    expired = app.create_session(principal)
    app.append_message(expired.session_id, "user", "private", principal)
    clock.advance(hours=2)
    active = app.create_session(principal)

    repository.purge_expired(clock())

    assert repository._connection.execute(
        "SELECT COUNT(*) FROM sessions WHERE session_id = ?", (str(expired.session_id),)
    ).fetchone()[0] == 0
    assert repository._connection.execute(
        "SELECT COUNT(*) FROM session_messages WHERE session_id = ?",
        (str(expired.session_id),),
    ).fetchone()[0] == 0
    assert repository._connection.execute(
        "SELECT COUNT(*) FROM sessions WHERE session_id = ?", (str(active.session_id),)
    ).fetchone()[0] == 1


def test_production_requires_a_long_hmac_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMPORIO_ENV", "production")
    monkeypatch.delenv("EMPORIO_PRINCIPAL_HMAC_SECRET", raising=False)
    with pytest.raises(ValueError, match="required in production"):
        principal_binding_secret()
    monkeypatch.setenv("EMPORIO_PRINCIPAL_HMAC_SECRET", "too-short")
    with pytest.raises(ValueError, match="at least 32"):
        principal_binding_secret()


def test_development_has_an_explicit_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMPORIO_ENV", "development")
    monkeypatch.delenv("EMPORIO_PRINCIPAL_HMAC_SECRET", raising=False)
    assert principal_binding_secret()


def test_session_reconnect_persists_same_sqlite_file(tmp_path: Path) -> None:
    clock = FakeClock()
    path = tmp_path / "persistent.db"
    principal = AuthorizedPrincipal(7)
    first_repository = SQLiteSessionRepository.connect(path)
    first = SessionService(first_repository, clock=clock).create_session(principal)
    SessionService(first_repository, clock=clock).append_message(
        first.session_id, "user", "kept", principal
    )
    second_repository = SQLiteSessionRepository.connect(path)
    restored = SessionService(second_repository, clock=clock).get_context(
        first.session_id, principal
    )
    assert [message.content for message in restored.messages] == ["kept"]
    assert restored.persistence is PersistenceState.PERSISTED


def test_repository_boundary_revalidates_control_safety(tmp_path: Path) -> None:
    clock = FakeClock()
    repository = SQLiteSessionRepository.connect(tmp_path / "boundary.db")
    principal = AuthorizedPrincipal(1)
    context = SessionService(repository, clock=clock).create_session(principal)
    message = SimpleNamespace(
        role=MessageRole.USER, content="unsafe\x00content", created_at=clock()
    )
    with pytest.raises(SessionValidationError):
        repository.append(context.session_id, principal, message, clock())


def test_expiry_cleanup_cascades_private_messages(tmp_path: Path) -> None:
    clock = FakeClock()
    limits = SessionLimits(ttl=timedelta(hours=1))
    repository = SQLiteSessionRepository.connect(tmp_path / "expired.db", limits)
    principal = AuthorizedPrincipal(1)
    app = SessionService(repository, limits=limits, clock=clock)
    context = app.create_session(principal)
    app.append_message(context.session_id, "user", "private", principal)
    clock.advance(hours=2)
    with pytest.raises(SessionExpiredError):
        repository.read(context.session_id, principal, clock())
    assert repository._connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    assert (
        repository._connection.execute("SELECT COUNT(*) FROM session_messages").fetchone()[0]
        == 0
    )


def test_malformed_expiry_is_storage_error(tmp_path: Path) -> None:
    clock = FakeClock()
    repository = SQLiteSessionRepository.connect(tmp_path / "malformed-expiry.db")
    principal = AuthorizedPrincipal(1)
    context = SessionService(repository, clock=clock).create_session(principal)
    repository._connection.execute(
        "UPDATE sessions SET expires_at = ? WHERE session_id = ?",
        ("not-a-timestamp", str(context.session_id)),
    )
    repository._connection.commit()
    with pytest.raises(SessionStorageError):
        repository.read(context.session_id, principal, clock())


def test_principal_binding_is_keyed_and_does_not_persist_raw_identity(tmp_path: Path) -> None:
    repository = SQLiteSessionRepository.connect(
        tmp_path / "binding.db", principal_secret=b"test-secret"
    )
    principal = AuthorizedPrincipal(123)
    context = SessionService(repository).create_session(principal)
    stored = repository._connection.execute(
        "SELECT principal_key FROM sessions WHERE session_id = ?", (str(context.session_id),)
    ).fetchone()[0]
    assert str(principal.customer_id) not in stored
    assert "123" not in stored
