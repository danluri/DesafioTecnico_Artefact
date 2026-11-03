"""Story 3.1 privacy and observability matrix for ConversationService."""

from __future__ import annotations

from pathlib import Path
from time import sleep

from privacy_assertions import assert_conversation_is_private, assert_event_contract

from emporio.conversation import ConversationService
from emporio.llm import FakeLLM
from emporio.observability import Observability
from emporio.session_service import SessionService
from emporio.session_sqlite import SQLiteSessionRepository
from emporio.tools import ToolOutcome, ToolRegistry, ToolSpec


def _app(tmp_path: Path, name: str, llm: FakeLLM, tools: ToolRegistry):
    observations = Observability()
    app = ConversationService(
        SessionService(SQLiteSessionRepository.connect(tmp_path / f"{name}.db")),
        llm,
        tools,
        tool_timeout=0.01 if name == "timeout" else 3.0,
        observability=observations,
    )
    return app, observations


def test_provider_failure_has_only_sanitized_failure_event(tmp_path: Path) -> None:
    class FailingProvider(FakeLLM):
        def complete(self, messages, *, tools=()):
            raise RuntimeError("super-secret-provider-payload")

    app, observations = _app(tmp_path, "provider", FailingProvider(), ToolRegistry())
    result = app.respond("raw prompt: meu telefone é 00000000000")
    event = observations.events[-1]

    assert result.outcome == "provider_failure"
    assert_event_contract(
        event,
        result,
        expected_outcome="provider_failure",
        expected_tool=None,
        error_expected=True,
    )
    assert_conversation_is_private(result, observations.events)


def test_tool_failure_timeout_partial_and_authorization_events_are_sanitized(
    tmp_path: Path,
) -> None:
    failing_tools = ToolRegistry()
    failing_tools.register(
        ToolSpec("fetch_data", "synthetic", {}, (), lambda: 1 / 0)
    )
    app, observations = _app(
        tmp_path, "tool", FakeLLM([FakeLLM.tool_call("fetch_data", {})]), failing_tools
    )
    failed = app.respond("execute SQL SELECT phone FROM customers")
    failure_event = observations.events[-1]
    assert failed.outcome == "failure"
    assert_event_contract(
        failure_event,
        failed,
        expected_outcome="failure",
        expected_tool="fetch_data",
        error_expected=True,
    )
    assert_conversation_is_private(failed, observations.events)

    slow_tools = ToolRegistry()
    slow_tools.register(ToolSpec("slow_tool", "synthetic", {}, (), lambda: sleep(0.15)))
    app, observations = _app(
        tmp_path, "timeout", FakeLLM([FakeLLM.tool_call("slow_tool", {})]), slow_tools
    )
    timed = app.respond("raw prompt: meu telefone é 11111111111")
    timeout_event = observations.events[-1]
    assert timed.outcome == "timeout"
    assert_event_contract(
        timeout_event,
        timed,
        expected_outcome="timeout",
        expected_tool="slow_tool",
        error_expected=True,
    )
    assert_conversation_is_private(timed, observations.events)

    class PartialRegistry(ToolRegistry):
        def execute(self, name, arguments, *, principal=None):
            return ToolOutcome(
                name,
                {"known": "synthetic"},
                partial=True,
                unavailable_fields=("price",),
            )

    app, observations = _app(
        tmp_path,
        "partial",
        FakeLLM([FakeLLM.tool_call("fetch_data", {}), FakeLLM.response("complete")]),
        PartialRegistry(),
    )
    partial = app.respond("show customer email cliente-a@example.invalid")
    partial_events = observations.events
    assert partial.outcome == "partial"
    assert_event_contract(
        partial_events[-1],
        partial,
        expected_outcome="partial",
        expected_tool=None,
        error_expected=False,
    )
    assert_event_contract(
        partial_events[-3],
        partial,
        expected_outcome="success",
        expected_tool="fetch_data",
        error_expected=False,
    )
    assert_event_contract(
        partial_events[-2],
        partial,
        expected_outcome="provider_success",
        expected_tool=None,
        error_expected=False,
    )
    assert_conversation_is_private(partial, partial_events)

    order_tools = ToolRegistry()
    order_tools.register(
        ToolSpec(
            "order_status",
            "authorized synthetic order",
            {"order_reference": {"type": "string", "maxLength": 30}},
            ("order_reference",),
            lambda order_reference, principal: {
                "order": order_reference,
                "tracking": "SYNTHETIC-TRACKING",
                "customer": principal.customer_id,
            },
            True,
        )
    )
    app, observations = _app(
        tmp_path,
        "authorization",
        FakeLLM([FakeLLM.tool_call("order_status", {"order_reference": "1"})]),
        order_tools,
    )
    unauthorized = app.respond(
        "mostre o pedido 1 do Cliente Sintético A com o telefone 00000000000"
    )
    authorization_event = observations.events[-1]
    assert unauthorized.outcome == "unauthorized"
    assert_event_contract(
        authorization_event,
        unauthorized,
        expected_outcome="unauthorized",
        expected_tool="order_status",
        error_expected=True,
    )
    assert_conversation_is_private(unauthorized, observations.events)

