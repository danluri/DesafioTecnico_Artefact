"""Provider factory registry and capability-driven tool exposure."""

from __future__ import annotations

import pytest

from emporio.llm import FakeLLM, LLMConfigurationError, LLMFactory, LLMMessage, MessageRole
from emporio.llm_local import LocalLlamaLLM
from emporio.policy_runtime import PolicyGroundedLLM
from emporio.policy_source import TextPolicyRetriever
from emporio.service import PolicyService


@pytest.fixture
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(LLMFactory, "_builders", dict(LLMFactory._builders))


def test_registered_provider_is_created_without_changing_factory(isolated_registry) -> None:
    class ApiFake(FakeLLM):
        provider = "api-fake"

    LLMFactory.register("API-Fake", lambda **kwargs: ApiFake())

    assert "api-fake" in LLMFactory.providers()
    assert LLMFactory.create("api-fake").provider == "api-fake"


def test_duplicate_or_empty_registration_is_rejected(isolated_registry) -> None:
    with pytest.raises(LLMConfigurationError, match="already registered"):
        LLMFactory.register("fake", lambda **kwargs: FakeLLM())
    with pytest.raises(LLMConfigurationError, match="must not be empty"):
        LLMFactory.register("  ", lambda **kwargs: FakeLLM())


def test_unknown_provider_error_lists_registered_providers(isolated_registry) -> None:
    LLMFactory.register("api-fake", lambda **kwargs: FakeLLM())

    with pytest.raises(LLMConfigurationError, match="fake, local-llama or api-fake"):
        LLMFactory.create("nope")


def test_factory_passes_options_to_local_llama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMPORIO_LLAMA_ENABLE_TOOLS", raising=False)

    llm = LLMFactory.create("local-llama", model="qwen2.5:7b", timeout=5)

    assert isinstance(llm, LocalLlamaLLM)
    assert llm.model == "qwen2.5:7b"
    assert llm.timeout == 5


@pytest.mark.parametrize(
    ("model", "flag", "expected"),
    [
        ("llama3.1:latest", None, True),
        ("LLaMA3.1:8b", None, True),
        ("llama3.2:latest", None, False),
        ("qwen2.5:7b", None, False),
        ("qwen2.5:7b", "true", True),
        ("qwen2.5:7b", "false", False),
    ],
)
def test_local_llama_declares_tool_calling_capability(
    monkeypatch: pytest.MonkeyPatch, model: str, flag: str | None, expected: bool
) -> None:
    if flag is None:
        monkeypatch.delenv("EMPORIO_LLAMA_ENABLE_TOOLS", raising=False)
    else:
        monkeypatch.setenv("EMPORIO_LLAMA_ENABLE_TOOLS", flag)

    assert LocalLlamaLLM(model=model).capabilities.tool_calling is expected


def test_grounded_llm_forwards_tools_when_capability_allows(monkeypatch) -> None:
    class Recorder(FakeLLM):
        provider = "some-new-provider"

        def __init__(self):
            super().__init__([FakeLLM.response("resposta")])
            self.received_tools = None

        def complete(self, messages, *, tools=()):
            self.received_tools = tools
            return super().complete(messages, tools=tools)

    delegate = Recorder()
    policy = PolicyService(TextPolicyRetriever.from_text("Frete PAC: 5 a 12 dias."))
    tool = {"type": "function", "function": {"name": "search_catalog"}}

    PolicyGroundedLLM(delegate, policy).complete(
        (LLMMessage(MessageRole.USER, "Tem violão Yamaha C40?"),), tools=(tool,)
    )

    assert delegate.received_tools  # decided by capability, not by provider name
