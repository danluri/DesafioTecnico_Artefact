"""Bounded conversation orchestration with honest safety outcomes."""
# ruff: noqa: E501

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from time import monotonic
from typing import Any
from uuid import uuid4

from .llm import LLMMessage, LLMPort
from .observability import Observability, SafetyEvent, elapsed_ms
from .order import AuthorizedPrincipal
from .session import PersistenceState, SessionAccessError, SessionId, SessionValidationError
from .session_service import SessionService
from .text import normalize_customer_text
from .tools import (
    ToolAuthorizationError,
    ToolExecutionError,
    ToolRegistry,
    ToolValidationError,
    UnknownToolError,
)


@dataclass(frozen=True, slots=True)
class ConversationOutcome:
    text: str
    session_id: SessionId
    correlation_id: str
    outcome: str
    tool_calls: int = 0
    partial: bool = False
    unavailable_fields: tuple[str, ...] = ()
    persistence: PersistenceState = PersistenceState.PERSISTED


class ConversationService:
    def __init__(
        self,
        sessions: SessionService,
        llm: LLMPort,
        tools: ToolRegistry,
        *,
        max_rounds=4,
        max_tool_calls=8,
        tool_timeout=3.0,
        observability: Observability | None = None,
    ) -> None:
        if min(max_rounds, max_tool_calls) < 1 or tool_timeout <= 0:
            raise ValueError("conversation budgets must be positive")
        self.sessions, self.llm, self.tools = sessions, llm, tools
        self.max_rounds, self.max_tool_calls, self.tool_timeout = (
            max_rounds,
            max_tool_calls,
            tool_timeout,
        )
        self.observability = observability or Observability()

    def respond(
        self,
        text: str,
        *,
        session_id: SessionId | str | None = None,
        principal: AuthorizedPrincipal | None = None,
    ) -> ConversationOutcome:
        correlation_id = str(uuid4())
        try:
            context = (
                self.sessions.create_session(principal)
                if session_id is None
                else self.sessions.get_context(session_id, principal)
            )
            context = self.sessions.append_message(
                context.session_id, "user", normalize_customer_text(text), principal
            )
        except (SessionAccessError, SessionValidationError):
            context = self.sessions.create_session(principal)
            result = "Não consegui acessar essa sessão. Iniciei uma nova sessão segura."
            context = self._persist(context, result, principal)
            return ConversationOutcome(
                result,
                context.session_id,
                correlation_id,
                "session_error",
                persistence=context.persistence,
            )
        session_hash = self.observability.hash_session(context.session_id)
        messages = tuple(LLMMessage(m.role.value, m.content) for m in context.messages)
        calls, partial, unavailable = 0, False, set()
        for _round in range(self.max_rounds):
            provider_started = monotonic()
            try:
                response = self.llm.complete(messages, tools=self.tools.schemas())
            except Exception as exc:
                self._event(
                    correlation_id, session_hash, None, "provider_failure", exc, provider_started
                )
                result = "Não consegui consultar o assistente agora. Tente novamente mais tarde."
                context = self._persist(context, result, principal)
                return ConversationOutcome(
                    result,
                    context.session_id,
                    correlation_id,
                    "provider_failure",
                    calls,
                    partial,
                    tuple(sorted(unavailable)),
                    context.persistence,
                )
            self._event(
                correlation_id, session_hash, None, "provider_success", None, provider_started
            )
            messages += (response.message,)
            if not response.tool_calls:
                result = (
                    "Encontrei apenas parte das informações permitidas. Alguns campos continuam indisponíveis no snapshot."
                    if partial
                    else normalize_customer_text(response.message.content)
                    or "Não consegui preparar uma resposta segura."
                )
                outcome = "partial" if partial else "success"
                self._event(correlation_id, session_hash, None, outcome, None)
                context = self._persist(context, result, principal)
                return ConversationOutcome(
                    result,
                    context.session_id,
                    correlation_id,
                    outcome,
                    calls,
                    partial,
                    tuple(sorted(unavailable)),
                    context.persistence,
                )
            for call in response.tool_calls:
                calls += 1
                if calls > self.max_tool_calls:
                    result = "A solicitação excedeu o limite seguro de operações."
                    self._event(correlation_id, session_hash, call.name, "round_budget", None)
                    context = self._persist(context, result, principal)
                    return ConversationOutcome(
                        result,
                        context.session_id,
                        correlation_id,
                        "round_budget",
                        calls - 1,
                        partial,
                        tuple(sorted(unavailable)),
                        context.persistence,
                    )
                started, failure_text, failure_outcome = monotonic(), None, None
                try:
                    outcome = self._execute(call.name, call.arguments, principal)
                    partial = partial or getattr(outcome, "partial", False)
                    unavailable.update(getattr(outcome, "unavailable_fields", ()))
                    content = outcome.as_text() if hasattr(outcome, "as_text") else str(outcome)
                    self._event(correlation_id, session_hash, call.name, "success", None, started)
                except UnknownToolError as exc:
                    content, failure_outcome = "Essa operação não está disponível.", "unsupported"
                    failure_text = content
                    self._event(
                        correlation_id, session_hash, call.name, failure_outcome, exc, started
                    )
                except ToolValidationError as exc:
                    content, failure_outcome = (
                        "Não consegui validar os dados necessários.",
                        "invalid_args",
                    )
                    failure_text = content
                    self._event(
                        correlation_id, session_hash, call.name, failure_outcome, exc, started
                    )
                except ToolAuthorizationError as exc:
                    content, failure_outcome = (
                        "Não posso consultar esse pedido sem autorização válida.",
                        "unauthorized",
                    )
                    failure_text = content
                    self._event(
                        correlation_id, session_hash, call.name, failure_outcome, exc, started
                    )
                except FutureTimeout as exc:
                    content, failure_outcome = (
                        "A operação demorou além do limite e não foi concluída.",
                        "timeout",
                    )
                    failure_text = content
                    self._event(
                        correlation_id, session_hash, call.name, failure_outcome, exc, started
                    )
                except ToolExecutionError as exc:
                    content, failure_outcome = (
                        "Não consegui obter essa informação agora.",
                        "failure",
                    )
                    failure_text = content
                    self._event(
                        correlation_id, session_hash, call.name, failure_outcome, exc, started
                    )
                messages += (LLMMessage("tool", content, tool_call_id=call.id),)
                context = self._persist(context, f"tool {call.name}: {content}", principal)
                if failure_text is not None:
                    return ConversationOutcome(
                        failure_text,
                        context.session_id,
                        correlation_id,
                        failure_outcome or "failure",
                        calls,
                        partial,
                        tuple(sorted(unavailable)),
                        context.persistence,
                    )
        result = "A conversa atingiu o limite seguro de etapas."
        self._event(correlation_id, session_hash, None, "round_budget", None)
        context = self._persist(context, result, principal)
        return ConversationOutcome(
            result,
            context.session_id,
            correlation_id,
            "round_budget",
            calls,
            partial,
            tuple(sorted(unavailable)),
            context.persistence,
        )

    handle = respond

    def _execute(self, name: str, arguments: Any, principal: AuthorizedPrincipal | None):
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self.tools.execute, name, arguments, principal=principal)
        try:
            return future.result(timeout=self.tool_timeout)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _persist(self, context, content: str, principal: AuthorizedPrincipal | None):
        try:
            return self.sessions.append_message(context.session_id, "assistant", content, principal)
        except (SessionAccessError, SessionValidationError):
            return context

    def _event(
        self,
        correlation: str,
        session_hash: str,
        tool: str | None,
        outcome: str,
        error: Exception | None,
        started: float | None = None,
    ) -> None:
        self.observability.emit(
            SafetyEvent(
                correlation,
                session_hash,
                getattr(self.llm, "provider", "unknown"),
                tool,
                elapsed_ms(started or monotonic()),
                outcome,
                type(error).__name__ if error else None,
            )
        )
