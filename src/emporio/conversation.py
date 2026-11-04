"""Bounded conversation orchestration with honest safety outcomes."""
# ruff: noqa: E501

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from contextvars import copy_context
import logging
import re
from time import monotonic
from typing import Any, Callable
from uuid import uuid4

from .llm import LLMMessage, LLMPort
from .tracing import traced_request, trace_id, event, fingerprint
from .catalog_search import grounded_search_arguments, grounded_payment_arguments
from .observability import Observability, SafetyEvent, elapsed_ms
from .order import AuthorizedPrincipal
from .session import PersistenceState, SessionAccessError, SessionId, SessionValidationError
from .session_service import SessionService
from .store_hours import NOTICE_MARKER
from .text import normalize_customer_text, is_system_failure_text
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
    catalog: dict[str, Any] | None = None
    trace: dict[str, Any] | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict, repr=False)


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
        hours_notice: Callable[[], str | None] | None = None,
    ) -> None:
        if min(max_rounds, max_tool_calls) < 1 or tool_timeout <= 0:
            raise ValueError("conversation budgets must be positive")
        self.sessions, self.llm, self.tools = sessions, llm, tools
        # Injected so tests stay clock-independent; the runtime passes store_hours.current_notice.
        self.hours_notice = hours_notice
        self.max_rounds, self.max_tool_calls, self.tool_timeout = (
            max_rounds,
            max_tool_calls,
            tool_timeout,
        )
        self.observability = observability or Observability()

    @traced_request
    def respond(
        self,
        text: str,
        *,
        session_id: SessionId | str | None = None,
        principal: AuthorizedPrincipal | None = None,
        message_id: str | None = None,
    ) -> ConversationOutcome:
        correlation_id = trace_id() or str(uuid4())
        session_started = monotonic()
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
        event('session_ready', duration_ms=elapsed_ms(session_started),
              persistence=context.persistence.value, session_hash=session_hash)
        simulator = getattr(self.tools, 'order_simulator', None)
        reference = re.search(r'\bSIM-\d{6,12}\b', text, re.IGNORECASE)
        if simulator and reference and re.search(r'reclama|devolu|devolv', text, re.IGNORECASE):
            from .order_simulation import SimulationError
            try:
                requests = simulator.post_sale(principal, reference.group())
                counts = {kind: sum(item['kind'] == kind for item in requests)
                          for kind in ('complaint', 'return')}
                result = (f"Pedido fictício {reference.group().upper()}: {counts['complaint']} reclamação(ões) e "
                          f"{counts['return']} pedido(s) de devolução registrados na simulação. "
                          "Para registrar uma solicitação, use os botões do console. "
                          "Os pedidos de devolução estão sujeitos a análise; nenhuma devolução real foi iniciada.")
                returns = [item for item in requests if item['kind'] == 'return']
                if returns:
                    latest = returns[-1]
                    result += (f" Última devolução: código fictício {latest['return_code']}. "
                               "Elegibilidade pendente. " + ' '.join(latest['instructions']))
                status = 'success'
            except SimulationError:
                result = 'Pedido de teste indisponível para este cliente.'
                status = 'unauthorized'
            context = self._persist(context, result, principal)
            return ConversationOutcome(result, context.session_id, correlation_id, status,
                                       persistence=context.persistence)
        messages = tuple(LLMMessage(m.role.value, m.content) for m in context.messages)
        calls, partial, unavailable = 0, False, set()
        catalog = None
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
                    catalog=catalog,
                )
            self._event(
                correlation_id, session_hash, None,
                'tool_planned' if response.usage.get('orchestrated_tool') else
                'clarification_required' if response.usage.get('orchestrated_reply') else
                'provider_fallback' if response.usage.get('calculated_fallback') or response.usage.get('grounded_fallback') else 'provider_success',
                None, provider_started
            )
            messages += (response.message,)
            if not response.tool_calls:
                result = (
                    "Encontrei apenas parte das informações permitidas. Alguns campos continuam indisponíveis no snapshot."
                    if partial
                    else normalize_customer_text(response.message.content)
                    or "Não consegui preparar uma resposta segura."
                )
                fallback = bool(response.usage.get('calculated_fallback') or response.usage.get('grounded_fallback'))
                failed_answer = is_system_failure_text(result)
                outcome = 'answer_failure' if failed_answer else "partial" if partial or fallback else "success"
                if failed_answer:
                    event('response_validation', status='failure', rule='model_returned_system_failure')
                else:
                    result = self._with_hours_notice(result, context)
                self._event(correlation_id, session_hash, None, outcome, None)
                context = self._persist(context, result, principal)
                return ConversationOutcome(
                    result,
                    context.session_id,
                    correlation_id,
                    outcome,
                    calls,
                    partial or fallback,
                    tuple(sorted(unavailable)),
                    context.persistence,
                    catalog=catalog,
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
                    arguments = (
                        grounded_search_arguments(text, dict(call.arguments))
                        if call.name == "search_catalog" else call.arguments
                    )
                    if call.name == 'calculate_payment' and catalog and len(catalog.get('products', [])) == 1:
                        arguments = grounded_payment_arguments(text, dict(arguments), catalog['products'][0]['product_id'])
                    event('tool_started', tool=call.name, argument_fields=sorted(arguments),
                          original_hash=fingerprint(call.arguments), effective_hash=fingerprint(arguments),
                          arguments_corrected=dict(call.arguments) != arguments)
                    outcome = self._execute(call.name, arguments, principal)
                    if call.name == "search_catalog" and isinstance(getattr(outcome, "value", None), dict):
                        catalog = outcome.value
                        event('catalog_result', total=catalog.get('total'),
                              returned=len(catalog.get('products', [])),
                              snapshot=catalog.get('snapshot'))
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

    def _with_hours_notice(self, result: str, context) -> str:
        """Manual 7.1: outside business hours, tell the customer when the team returns (once)."""
        if self.hours_notice is None:
            return result
        notice = self.hours_notice()
        if not notice:
            return result
        already_told = any(
            m.role.value == "assistant" and NOTICE_MARKER in m.content for m in context.messages
        )
        if already_told:
            return result
        event('hours_notice', status='appended')
        return f"{result}\n\n{notice}"

    def _execute(self, name: str, arguments: Any, principal: AuthorizedPrincipal | None):
        executor = ThreadPoolExecutor(max_workers=1)
        context = copy_context()
        future = executor.submit(context.run, self.tools.execute, name, arguments, principal=principal)
        try:
            return future.result(timeout=self.tool_timeout)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _persist(self, context, content: str, principal: AuthorizedPrincipal | None):
        started = monotonic()
        try:
            result = self.sessions.append_message(context.session_id, "assistant", content, principal)
            event('persistence', status=result.persistence.value, duration_ms=elapsed_ms(started))
            return result
        except (SessionAccessError, SessionValidationError) as exc:
            event('persistence', status='failure', duration_ms=elapsed_ms(started), error_class=type(exc).__name__)
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
        event('tool_completed' if tool else 'conversation_event', status=outcome,
              duration_ms=elapsed_ms(started or monotonic()), tool=tool,
              error_class=type(error).__name__ if error else None,
              cause_class=type(error.__cause__).__name__ if error and error.__cause__ else None)
        logging.getLogger("emporio.local_llama").info(
            "conversation_event correlation=%s tool=%s outcome=%s error=%s cause=%s",
            correlation, tool, outcome,
            type(error).__name__ if error else None,
            type(error.__cause__).__name__ if error and error.__cause__ else None,
        )
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
