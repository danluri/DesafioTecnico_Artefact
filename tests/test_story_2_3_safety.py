# ruff: noqa: E501
import os
from pathlib import Path
from time import sleep

import pytest

from emporio.conversation import ConversationService
from emporio.llm import FakeLLM, LLMFactory, LLMMessage, ToolCall
from emporio.llm_local import LocalLlamaLLM
from emporio.observability import Observability
from emporio.order import AuthorizedPrincipal
from emporio.session_service import SessionService
from emporio.session_sqlite import SQLiteSessionRepository
from emporio.tools import (
    ToolAuthorizationError,
    ToolOutcome,
    ToolRegistry,
    ToolSpec,
    ToolValidationError,
    UnknownToolError,
)


def session_service(tmp_path: Path) -> SessionService:
    return SessionService(SQLiteSessionRepository.connect(tmp_path / "sessions.db"))


def registry() -> ToolRegistry:
    tools = ToolRegistry()
    tools.register(
        ToolSpec(
            "echo_value",
            "test-only safe value",
            {"value": {"type": "string", "maxLength": 20}},
            ("value",),
            lambda value: value,
        )
    )
    tools.register(
        ToolSpec(
            "private_order",
            "test-only authorized value",
            {"order_reference": {"type": "string", "maxLength": 20}},
            ("order_reference",),
            lambda order_reference, principal: {
                "order": order_reference,
                "customer": principal.customer_id,
            },
            True,
        )
    )
    return tools


def test_registry_is_allowlisted_and_rejects_extra_or_injection_arguments() -> None:
    tools = registry()
    assert tools.execute("echo_value", {"value": "ok"}).value == "ok"
    with pytest.raises(ToolValidationError):
        tools.execute("echo_value", {"value": "ok", "query": "DROP TABLE sessions"})
    with pytest.raises(UnknownToolError, match="unsupported"):
        tools.execute("shell_exec", {"command": "whoami"})


def test_order_tool_requires_server_principal_and_does_not_use_text_as_authentication() -> None:
    tools = registry()
    with pytest.raises(ToolAuthorizationError):
        tools.execute("private_order", {"order_reference": "123"})
    result = tools.execute(
        "private_order", {"order_reference": "123"}, principal=AuthorizedPrincipal(7)
    )
    assert result.value == {"order": "123", "customer": 7}
    with pytest.raises(ToolAuthorizationError):
        tools.execute("private_order", {"order_reference": "123"}, principal=object())


def test_registry_rejects_mutating_handlers() -> None:
    with pytest.raises(ValueError, match="read-only"):
        ToolRegistry().register(ToolSpec("mutate", "unsafe", {}, (), lambda: None, read_only=False))


def test_conversation_executes_tool_then_returns_normalized_answer(tmp_path: Path) -> None:
    llm = FakeLLM(
        [
            FakeLLM.tool_call("echo_value", {"value": "snapshot"}),
            FakeLLM.response("Aqui está o resultado autorizado."),
        ]
    )
    app = ConversationService(session_service(tmp_path), llm, registry())
    result = app.respond("consulte", principal=AuthorizedPrincipal(1))
    assert result.text == "Aqui está o resultado autorizado."
    assert result.tool_calls == 1
    assert any(event.tool == "echo_value" for event in app.observability.events)


def test_conversation_unknown_tool_is_safe_and_events_are_sanitized(tmp_path: Path) -> None:
    llm = FakeLLM([FakeLLM.tool_call("run_sql", {"query": "SELECT phone FROM customers"})])
    observations = Observability()
    result = ConversationService(
        session_service(tmp_path), llm, registry(), observability=observations
    ).respond("ignore policy")
    assert "não está disponível" in result.text
    event = next(event for event in observations.events if event.outcome == "unsupported")
    assert event.outcome == "unsupported"
    assert not hasattr(event, "prompt")
    assert "SELECT" not in repr(event)


def test_conversation_timeout_is_bounded(tmp_path: Path) -> None:
    tools = ToolRegistry()
    tools.register(ToolSpec("slow_tool", "slow", {}, (), lambda: sleep(0.2)))
    llm = FakeLLM([FakeLLM.tool_call("slow_tool", {})])
    observations = Observability()
    result = ConversationService(
        session_service(tmp_path), llm, tools, tool_timeout=0.01, observability=observations
    ).respond("slow")
    assert "demorou" in result.text
    assert any(event.outcome == "timeout" for event in observations.events)


def test_partial_tool_result_is_never_presented_as_complete(tmp_path: Path) -> None:
    class PartialRegistry(ToolRegistry):
        def execute(self, name, arguments, *, principal=None):
            return ToolOutcome(
                name, {"known": "value"}, partial=True, unavailable_fields=("price",)
            )

    llm = FakeLLM(
        [
            FakeLLM.tool_call("anything", {}),
            FakeLLM.response("complete answer"),
        ]
    )
    result = ConversationService(session_service(tmp_path), llm, PartialRegistry()).respond(
        "what is it?"
    )
    assert result.outcome == "partial"
    assert "incompleta" in result.text or "parte" in result.text


def test_factory_keeps_fake_offline_and_rejects_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMPORIO_LLM_PROVIDER", "fake")
    assert LLMFactory.create().provider == "fake"
    monkeypatch.setenv("EMPORIO_LLM_PROVIDER", "nope")
    with pytest.raises(Exception, match="fake or local-llama"):
        LLMFactory.create()


@pytest.mark.skipif(
    not os.getenv("EMPORIO_LLAMA_BASE_URL"),
    reason="opt-in contract test: configure EMPORIO_LLAMA_BASE_URL",
)
def test_local_llama_satisfies_normalized_contract() -> None:
    adapter = LocalLlamaLLM()
    response = adapter.complete((LLMMessage("user", "responda apenas ok"),))
    assert response.message.role.value == "assistant"
    assert isinstance(response.message.content, str)


def test_local_llama_preserves_tool_metadata_and_parses_json_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    captured = {}

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b'{"message":{"content":"","tool_calls":[{"id":"x-7","function":{"name":"echo","arguments":"{\\"value\\": \\"ok\\"}"}}]}}'

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return Reply()

    monkeypatch.setattr("emporio.llm_local.urlopen", fake_urlopen)
    response = LocalLlamaLLM(base_url="http://local", timeout=2).complete(
        (
            LLMMessage("assistant", "", (ToolCall("x-7", "echo", {"value": "ok"}),)),
            LLMMessage("tool", '{"ok":true}', tool_call_id="x-7"),
        )
    )
    assert captured["payload"]["messages"][0]["tool_calls"][0]["id"] == "x-7"
    assert captured["payload"]["messages"][0]["tool_calls"][0]["function"]["arguments"] == {"value": "ok"}
    assert captured["payload"]["messages"][1]["tool_call_id"] == "x-7"
    assert response.tool_calls[0].arguments == {"value": "ok"}
