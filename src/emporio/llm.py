"""Provider-neutral language-model contracts and deterministic offline adapter."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Mapping, Sequence

from .text import normalize_customer_text


class LLMError(Exception):
    """A provider could not produce a normalized response."""


class LLMConfigurationError(LLMError):
    """Provider configuration is unsupported or incomplete."""


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: MessageRole | str
    content: str = ""
    tool_calls: tuple["ToolCall", ...] = ()
    tool_call_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content, str):
            raise TypeError("message content must be text")
        object.__setattr__(self, "role", MessageRole(self.role))


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool_call_id: str
    name: str
    content: str
    ok: bool = True


@dataclass(frozen=True, slots=True)
class LLMResponse:
    message: LLMMessage
    finish_reason: str = "stop"
    usage: Mapping[str, int] = field(default_factory=dict)

    @property
    def tool_calls(self) -> tuple[ToolCall, ...]:
        return self.message.tool_calls


@dataclass(frozen=True, slots=True)
class LLMCapabilities:
    tool_calling: bool = True
    structured_output: bool = False


class LLMPort:
    """Small normalized port implemented by every model adapter."""

    provider = "unknown"
    model = "unknown"
    capabilities = LLMCapabilities()

    def complete(
        self, messages: Sequence[LLMMessage], *, tools: Sequence[Mapping[str, Any]] = ()
    ) -> LLMResponse:
        raise NotImplementedError


class FakeLLM(LLMPort):
    """Deterministic response queue for offline tests and local development."""

    provider = "fake"
    model = "fake"

    def __init__(
        self, responses: Sequence[LLMResponse] | None = None, *, scenario: str = ""
    ) -> None:
        self._responses = list(responses or self.scenario(scenario))
        self.calls: list[tuple[LLMMessage, ...]] = []

    @staticmethod
    def response(text: str) -> LLMResponse:
        return LLMResponse(LLMMessage(MessageRole.ASSISTANT, normalize_customer_text(text)))

    @staticmethod
    def tool_call(
        name: str, arguments: Mapping[str, Any], *, call_id: str = "call-1"
    ) -> LLMResponse:
        call = ToolCall(call_id, name, dict(arguments))
        return LLMResponse(LLMMessage(MessageRole.ASSISTANT, "", (call,)), "tool_calls")

    @classmethod
    def scenario(cls, name: str) -> list[LLMResponse]:
        scenarios = {
            "unsupported": [cls.response("Não consigo executar essa ação por este canal.")],
            "unknown-tool": [cls.tool_call("run_sql", {"query": "DROP TABLE orders"})],
            "catalog-search": [cls.tool_call("search_catalog", {"name": "violão"})],
        }
        if name and name not in scenarios:
            raise LLMConfigurationError(f"unknown FakeLLM scenario: {name}")
        return list(scenarios.get(name, ()))

    def complete(
        self, messages: Sequence[LLMMessage], *, tools: Sequence[Mapping[str, Any]] = ()
    ) -> LLMResponse:
        self.calls.append(tuple(messages))
        if not self._responses:
            return self.response("Não consegui concluir a resposta com segurança.")
        return self._responses.pop(0)


ProviderBuilder = Callable[..., LLMPort]


def _build_fake(**kwargs: Any) -> LLMPort:
    return FakeLLM(kwargs.get("responses"), scenario=kwargs.get("scenario", ""))


def _build_local_llama(**kwargs: Any) -> LLMPort:
    # Lazy import keeps the offline/fake path free of the HTTP adapter.
    from .llm_local import LocalLlamaLLM

    return LocalLlamaLLM(
        base_url=kwargs.get("base_url"),
        model=kwargs.get("model"),
        timeout=kwargs.get("timeout"),
    )


class LLMFactory:
    """Registry-based factory: only explicitly registered providers can be created.

    Adding a provider means implementing ``LLMPort`` and calling ``register`` once;
    ``create`` and its callers do not change.
    """

    _builders: dict[str, ProviderBuilder] = {
        "fake": _build_fake,
        "local-llama": _build_local_llama,
    }

    @classmethod
    def register(cls, name: str, builder: ProviderBuilder) -> None:
        key = name.strip().lower()
        if not key:
            raise LLMConfigurationError("provider name must not be empty")
        if key in cls._builders:
            raise LLMConfigurationError(f"provider already registered: {key}")
        cls._builders[key] = builder

    @classmethod
    def providers(cls) -> tuple[str, ...]:
        return tuple(cls._builders)

    @classmethod
    def create(cls, provider: str | None = None, **kwargs: Any) -> LLMPort:
        selected = (provider or os.getenv("EMPORIO_LLM_PROVIDER", "fake")).strip().lower()
        builder = cls._builders.get(selected)
        if builder is None:
            *others, last = cls.providers()
            allowed = f"{', '.join(others)} or {last}" if others else last
            raise LLMConfigurationError(f"EMPORIO_LLM_PROVIDER must be {allowed}")
        return builder(**kwargs)
