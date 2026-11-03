"""Optional local Llama/Ollama-compatible HTTP adapter using only the stdlib."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from urllib.error import URLError
from urllib.request import Request, urlopen

from .llm import LLMError, LLMMessage, LLMPort, LLMResponse, MessageRole, ToolCall


class LocalLlamaUnavailable(LLMError):
    """The configured local endpoint did not answer successfully."""


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
        self.model = model or os.getenv("EMPORIO_LLAMA_MODEL", "llama3.2")
        self.timeout = float(timeout or os.getenv("EMPORIO_LLAMA_TIMEOUT", "10"))
        if self.timeout <= 0:
            raise ValueError("EMPORIO_LLAMA_TIMEOUT must be positive")

    def complete(self, messages: Sequence[LLMMessage], *, tools=()) -> LLMResponse:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [_serialize_message(m) for m in messages],
        }
        if tools:
            payload["tools"] = list(tools)
        request = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
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
                "function": {"name": call.name, "arguments": json.dumps(dict(call.arguments))},
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
