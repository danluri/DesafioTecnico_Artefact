"""Optional local Llama/Ollama-compatible HTTP adapter using only the stdlib."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .llm import (
    LLMCapabilities,
    LLMError,
    LLMMessage,
    LLMPort,
    LLMResponse,
    MessageRole,
    ToolCall,
)
from .tracing import runtime_logger, event, diagnostic

# Models verified to follow Ollama tool calling reliably; others need explicit opt-in.
TOOL_CALLING_MODEL_PREFIXES = ("llama3.1",)


def local_tool_calling_supported(model: str) -> bool:
    """Tool calling is on for known-capable models or when explicitly enabled."""
    enabled = os.getenv("EMPORIO_LLAMA_ENABLE_TOOLS", "false").strip().lower()
    if enabled in {"1", "true", "yes", "on"}:
        return True
    return model.strip().lower().startswith(TOOL_CALLING_MODEL_PREFIXES)


class LocalLlamaUnavailable(LLMError):
    """The configured local endpoint did not answer successfully."""


def _runtime_logger() -> logging.Logger:
    return runtime_logger()


class LocalLlamaLLM(LLMPort):
    provider = "local-llama"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | str | None = None,
    ) -> None:
        self.base_url = (
            base_url or os.getenv("EMPORIO_LLAMA_BASE_URL", "http://127.0.0.1:11434")
        ).rstrip("/")
        self.model = model or os.getenv("EMPORIO_LLAMA_MODEL", "llama3.1:latest")
        self.timeout = float(timeout or os.getenv("EMPORIO_LLAMA_TIMEOUT", "180"))
        self.last_error = ""
        self.capabilities = LLMCapabilities(
            tool_calling=local_tool_calling_supported(self.model)
        )
        if self.timeout <= 0:
            raise ValueError("EMPORIO_LLAMA_TIMEOUT must be positive")

    def complete(self, messages: Sequence[LLMMessage], *, tools=()) -> LLMResponse:
        self.last_error = ""
        diagnostic(provider_error=None, provider_timeout=self.timeout)
        logger = _runtime_logger()
        started = monotonic()
        payload = {
            "model": self.model,
            "stream": False,
            "options": {"num_predict": int(os.getenv("EMPORIO_LLAMA_MAX_TOKENS", "512"))},
            "messages": [_serialize_message(m) for m in messages],
        }
        if tools:
            payload["tools"] = list(tools)
        event('llm_started', provider=self.provider, model=self.model, messages=len(messages),
              prompt_chars=sum(len(m.content) for m in messages), timeout=self.timeout,
              tools=[tool.get('function', {}).get('name') for tool in tools])
        logger.info(
            "llama_request model=%s messages=%d prompt_chars=%d tools=%s timeout=%s",
            self.model,
            len(messages),
            sum(len(message.content) for message in messages),
            [tool.get("function", {}).get("name") for tool in tools],
            self.timeout,
        )
        request = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            event('llm_completed', duration_ms=int((monotonic()-started)*1000),
                  model=self.model, prompt_tokens=data.get('prompt_eval_count'),
                  generated_tokens=data.get('eval_count'),
                  load_ms=data.get('load_duration', 0)/1_000_000,
                  prompt_ms=data.get('prompt_eval_duration', 0)/1_000_000,
                  generation_ms=data.get('eval_duration', 0)/1_000_000,
                  provider_total_ms=data.get('total_duration', 0)/1_000_000)
            logger.info(
                "llama_response model=%s elapsed_ms=%d tool_calls=%d content_chars=%d",
                self.model,
                int((monotonic() - started) * 1000),
                len(data.get("message", {}).get("tool_calls", ())),
                len(data.get("message", {}).get("content", "")),
            )
            logger.info(
                "llama_metrics model=%s load_ms=%s prompt_tokens=%s prompt_ms=%s "
                "generated_tokens=%s generation_ms=%s total_ms=%s",
                self.model,
                data.get("load_duration", 0) / 1_000_000,
                data.get("prompt_eval_count"),
                data.get("prompt_eval_duration", 0) / 1_000_000,
                data.get("eval_count"),
                data.get("eval_duration", 0) / 1_000_000,
                data.get("total_duration", 0) / 1_000_000,
            )
        except HTTPError as exc:
            self.last_error = f"HTTPError:{exc.code}"
            diagnostic(provider_error=self.last_error)
            event('llm_error', status='failure', duration_ms=int((monotonic()-started)*1000),
                  error_class='HTTPError', http_status=exc.code)
            logger.error(
                "llama_http_error model=%s elapsed_ms=%d error=%s",
                self.model,
                int((monotonic() - started) * 1000),
                self.last_error,
            )
            raise LocalLlamaUnavailable("local Llama endpoint rejected the request") from exc
        except (OSError, URLError, TimeoutError, ValueError, TypeError, AttributeError, json.JSONDecodeError) as exc:
            self.last_error = type(exc).__name__
            diagnostic(provider_error=self.last_error)
            event('llm_error', status='failure', duration_ms=int((monotonic()-started)*1000),
                  error_class=self.last_error)
            logger.error(
                "llama_request_error model=%s elapsed_ms=%d error=%s",
                self.model,
                int((monotonic() - started) * 1000),
                self.last_error,
            )
            raise LocalLlamaUnavailable("local Llama endpoint unavailable") from exc
        try:
            message = data["message"]
            calls = tuple(
                ToolCall(
                    str(item.get("id", f"call-{index}")),
                    str(item["function"]["name"]),
                    _parse_arguments(item["function"].get("arguments", {})),
                )
                for index, item in enumerate(message.get("tool_calls", ()), 1)
            )
            return LLMResponse(
                LLMMessage(MessageRole.ASSISTANT, message.get("content", ""), calls),
                "tool_calls" if calls else "stop",
                data.get("prompt_eval_count", {})
                if isinstance(data.get("prompt_eval_count", {}), dict)
                else {},
            )
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            self.last_error = type(exc).__name__
            diagnostic(provider_error=self.last_error)
            event('llm_error', status='failure', error_class=self.last_error)
            logger.error(
                "llama_response_error model=%s elapsed_ms=%d error=%s",
                self.model,
                int((monotonic() - started) * 1000),
                self.last_error,
            )
            raise LocalLlamaUnavailable("local Llama returned an invalid response") from exc


def _serialize_message(message: LLMMessage) -> dict[str, object]:
    payload: dict[str, object] = {
        "role": message.role.value,
        "content": message.content,
    }
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                    "function": {"name": call.name, "arguments": dict(call.arguments)},
            }
            for call in message.tool_calls
        ]
    if message.role is MessageRole.TOOL:
        if not message.tool_call_id:
            raise ValueError("tool messages require a tool call id")
        payload["tool_call_id"] = message.tool_call_id
    return payload


def _parse_arguments(arguments: object) -> dict[str, object]:
    if isinstance(arguments, str):
        parsed = json.loads(arguments)
        if not isinstance(parsed, dict):
            raise ValueError("provider tool arguments must be a JSON object")
        return parsed
    if isinstance(arguments, dict):
        return arguments
    raise ValueError("provider tool arguments must be an object")
