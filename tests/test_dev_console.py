import json
import sys
import threading
from http.client import HTTPConnection
from pathlib import Path

import pytest

from emporio import runtime
from emporio.conversation import ConversationService
from emporio.dev_console import DevConsoleApplication, create_server, serve
from emporio.llm import FakeLLM
from emporio.session_service import SessionService
from emporio.session_sqlite import SQLiteSessionRepository
from emporio.tools import ToolRegistry


def application(tmp_path: Path) -> DevConsoleApplication:
    sessions = SessionService(SQLiteSessionRepository.connect(tmp_path / "sessions.db"))
    conversation = ConversationService(
        sessions,
        FakeLLM([FakeLLM.response("Primeira resposta."), FakeLLM.response("Segunda resposta.")]),
        ToolRegistry(),
    )
    return DevConsoleApplication(conversation, str(tmp_path / "whatsapp.db"))


def request(port: int, path: str, payload: dict | None = None):
    connection = HTTPConnection("127.0.0.1", port)
    if payload is None:
        connection.request("GET", path)
    else:
        body = json.dumps(payload).encode()
        connection.request("POST", path, body=body, headers={"Content-Type": "application/json"})
    response = connection.getresponse()
    data = response.read()
    content_type = response.getheader("Content-Type", "")
    connection.close()
    return response.status, json.loads(data) if "application/json" in content_type else data


def test_console_serves_browser_and_health(tmp_path: Path) -> None:
    server = create_server(application(tmp_path), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        status, html = request(port, "/")
        assert status == 200
        assert "Console de teste" in html.decode("utf-8")
        status, health = request(port, "/health")
        assert status == 200 and health["mode"] == "development"
    finally:
        server.shutdown()
        server.server_close()


def test_console_routes_message_session_and_duplicate(tmp_path: Path) -> None:
    server = create_server(application(tmp_path), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    payload = {"message_id": "dev-1", "sender": "5511999999999", "text": "oi"}
    try:
        status, first = request(port, "/api/messages", payload)
        assert status == 200
        assert first["response"] == "Primeira resposta."
        assert first["session_id"]
        assert first["provider"] == "fake"

        follow_up = {
            **payload,
            "message_id": "dev-2",
            "session_id": first["session_id"],
            "text": "tudo bem?",
        }
        status, second = request(port, "/api/messages", follow_up)
        assert status == 200 and second["response"] == "Segunda resposta."

        status, duplicate = request(port, "/api/messages", follow_up)
        assert status == 200 and duplicate["duplicate"] is True
        assert duplicate["response"] is None
    finally:
        server.shutdown()
        server.server_close()


def test_console_rejects_malformed_and_oversized_messages(tmp_path: Path) -> None:
    server = create_server(application(tmp_path), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        status, body = request(port, "/api/messages", {"text": ""})
        assert status == 400 and "error" in body
        status, body = request(port, "/unknown", {"text": "oi"})
        assert status == 404 and "error" in body
    finally:
        server.shutdown()
        server.server_close()


def test_console_requires_explicit_enablement(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMPORIO_DEV_CONSOLE_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="EMPORIO_DEV_CONSOLE_ENABLED"):
        serve(object())


def test_console_returns_bounded_error_when_conversation_raises(tmp_path: Path) -> None:
    class BrokenConversation:
        llm = FakeLLM()

        def respond(self, text, **kwargs):
            raise RuntimeError("provider details must not escape")

    app = DevConsoleApplication(BrokenConversation(), str(tmp_path / "events.db"))
    server = create_server(app, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, body = request(
            server.server_address[1],
            "/api/messages",
            {"message_id": "broken-1", "sender": "5511999999999", "text": "oi"},
        )
        assert status == 503 and body == {"error": "conversation unavailable"}
    finally:
        server.shutdown()
        server.server_close()


def test_runtime_dev_console_route_is_explicit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    called = []
    monkeypatch.setenv("EMPORIO_DB_PATH", str(tmp_path / "runtime.db"))
    monkeypatch.setenv("EMPORIO_DEV_CONSOLE_ENABLED", "true")
    monkeypatch.setattr(sys, "argv", ["emporio.runtime", "--dev-console"])
    monkeypatch.setattr(runtime, "serve", lambda application: called.append(application))

    runtime.main()

    assert len(called) == 1
