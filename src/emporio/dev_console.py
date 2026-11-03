"""Local-only development console for exercising the real conversation pipeline."""
# ruff: noqa: E501

from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .config import database_path
from .conversation import ConversationService
from .llm import LLMFactory
from .session_service import SessionService
from .session_sqlite import SQLiteSessionRepository
from .simulators import MockWhatsAppChannel, mock_whatsapp_config
from .tools import ToolRegistry
from .whatsapp import WhatsAppWebhookAdapter, WhatsAppVerificationError

MAX_BODY_BYTES = 64 * 1024
MAX_TEXT_CHARS = 4000
MAX_FIELD_CHARS = 200
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080


HTML = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Empório — Console de teste</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, system-ui, sans-serif; }
    body { margin: 0; background: #111827; color: #e5e7eb; }
    main { max-width: 900px; margin: 0 auto; padding: 32px 20px; }
    h1 { margin: 0 0 8px; font-size: 28px; }
    .muted { color: #9ca3af; }
    .panel { background: #1f2937; border: 1px solid #374151; border-radius: 14px; padding: 18px; margin-top: 18px; }
    label { display: block; margin: 12px 0 6px; color: #d1d5db; }
    input, textarea, button { box-sizing: border-box; width: 100%; border-radius: 8px; border: 1px solid #4b5563; padding: 10px; font: inherit; }
    input, textarea { background: #111827; color: #f9fafb; }
    textarea { min-height: 110px; resize: vertical; }
    button { margin-top: 14px; background: #f59e0b; color: #111827; border: 0; font-weight: 700; cursor: pointer; }
    button:hover { background: #fbbf24; }
    pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #030712; border-radius: 8px; padding: 14px; min-height: 80px; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    @media (max-width: 650px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
<main>
  <h1>Console de teste do Empório</h1>
  <p class="muted">Fluxo local: WhatsApp simulado → ConversationService → LLM → SQLite.</p>
  <section class="panel">
    <div class="grid">
      <div><label for="sender">Remetente</label><input id="sender" value="5511999999999"></div>
      <div><label for="messageId">ID da mensagem</label><input id="messageId"></div>
    </div>
    <label for="sessionId">Sessão (preenchida automaticamente)</label>
    <input id="sessionId" placeholder="nova sessão">
    <label for="text">Mensagem</label>
    <textarea id="text" placeholder="Ex.: Qual é o prazo de entrega para São Paulo?"></textarea>
    <button id="send">Enviar mensagem simulada</button>
  </section>
  <section class="panel">
    <h2>Resposta</h2>
    <pre id="response">Aguardando mensagem...</pre>
  </section>
</main>
<script>
const id = (name) => document.getElementById(name);
id('messageId').value = 'dev-' + crypto.randomUUID();
id('send').addEventListener('click', async () => {
  const payload = {
    sender: id('sender').value,
    message_id: id('messageId').value,
    session_id: id('sessionId').value || null,
    text: id('text').value
  };
  id('response').textContent = 'Processando...';
  try {
    const result = await fetch('/api/messages', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
    });
    const data = await result.json();
    if (data.session_id) id('sessionId').value = data.session_id;
    id('response').textContent = JSON.stringify(data, null, 2);
  } catch (error) { id('response').textContent = 'Falha de conexão: ' + error; }
});
</script>
</body>
</html>"""


def _flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "on"}


def _bounded_text(value: Any, field: str, maximum: int = MAX_FIELD_CHARS) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field} is required and bounded")
    return value.strip()


class _SessionConversation:
    def __init__(self, service: ConversationService, session_id: str | None) -> None:
        self.service, self.session_id = service, session_id or None

    def respond(self, text: str) -> Any:
        return self.service.respond(text, session_id=self.session_id)


class DevConsoleApplication:
    def __init__(self, conversation: ConversationService, idempotency_db: str | None = None) -> None:
        self.conversation = conversation
        path = idempotency_db or os.getenv("EMPORIO_DEV_IDEMPOTENCY_DB")
        if not path:
            path = str(database_path().with_name("dev-whatsapp-events.db"))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.channel = MockWhatsAppChannel(
            WhatsAppWebhookAdapter(mock_whatsapp_config(idempotency_db_path=path))
        )

    def message(self, payload: Any) -> tuple[int, dict[str, Any]]:
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        text = _bounded_text(payload.get("text"), "text", MAX_TEXT_CHARS)
        message_id = _bounded_text(payload.get("message_id"), "message_id")
        sender = _bounded_text(payload.get("sender", "5511999999999"), "sender")
        session_id = payload.get("session_id")
        if session_id is not None:
            session_id = _bounded_text(session_id, "session_id")
        result = self.channel.deliver(
            _SessionConversation(self.conversation, session_id),
            message_id=message_id,
            sender=sender,
            text=text,
        )
        outcome = result.response
        response_session = getattr(outcome, "session_id", session_id)
        body = {
            "accepted": result.accepted,
            "duplicate": result.duplicate,
            "message_id": result.message.message_id if result.message else message_id,
            "session_id": str(response_session) if response_session is not None else None,
            "response": getattr(outcome, "text", None),
            "outcome": getattr(outcome, "outcome", "duplicate" if result.duplicate else None),
            "provider": getattr(self.conversation.llm, "provider", "unknown"),
            "model": getattr(self.conversation.llm, "model", "unknown"),
            "tool_calls": getattr(outcome, "tool_calls", 0),
            "persistence": getattr(getattr(outcome, "persistence", None), "value", None),
        }
        return HTTPStatus.OK, body


def create_default_application() -> DevConsoleApplication:
    repository = SQLiteSessionRepository.connect(database_path())
    return DevConsoleApplication(
        ConversationService(SessionService(repository), LLMFactory.create(), ToolRegistry())
    )


def create_server(application: DevConsoleApplication, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("development console must bind to localhost")

    class Handler(BaseHTTPRequestHandler):
        server_version = "EmporioDevConsole/1.0"

        def _write(self, status: int, body: Any, content_type: str = "application/json") -> None:
            raw = body.encode("utf-8") if isinstance(body, str) else json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                self._write(HTTPStatus.OK, HTML, "text/html")
            elif self.path == "/health":
                self._write(HTTPStatus.OK, {"status": "ok", "mode": "development"})
            else:
                self._write(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/messages":
                self._write(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            length = self.headers.get("Content-Length", "")
            try:
                size = int(length)
            except ValueError:
                size = 0
            if not 1 <= size <= MAX_BODY_BYTES:
                self._write(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request body is invalid"})
                return
            try:
                payload = json.loads(self.rfile.read(size).decode("utf-8"))
                status, body = application.message(payload)
            except (UnicodeError, json.JSONDecodeError, ValueError, WhatsAppVerificationError):
                status, body = HTTPStatus.BAD_REQUEST, {"error": "invalid development message"}
            except Exception:  # noqa: BLE001 - never leak a development traceback
                status, body = HTTPStatus.SERVICE_UNAVAILABLE, {"error": "conversation unavailable"}
            self._write(status, body)

        def _method_not_allowed(self) -> None:
            self._write(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method not allowed"})

        do_PUT = _method_not_allowed
        do_PATCH = _method_not_allowed
        do_DELETE = _method_not_allowed

        def log_message(self, *_args: Any) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def serve(application: DevConsoleApplication | None = None) -> ThreadingHTTPServer:
    if not _flag("EMPORIO_DEV_CONSOLE_ENABLED"):
        raise RuntimeError("set EMPORIO_DEV_CONSOLE_ENABLED=true to enable the dev console")
    raw_port = os.getenv("EMPORIO_DEV_CONSOLE_PORT")
    if not raw_port:
        raise RuntimeError("set EMPORIO_DEV_CONSOLE_PORT to enable the dev console")
    try:
        port = int(raw_port)
    except ValueError:
        raise ValueError("EMPORIO_DEV_CONSOLE_PORT must be an integer") from None
    if not 1 <= port <= 65535:
        raise ValueError("EMPORIO_DEV_CONSOLE_PORT must be between 1 and 65535")
    server = create_server(application or create_default_application(), DEFAULT_HOST, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return server
