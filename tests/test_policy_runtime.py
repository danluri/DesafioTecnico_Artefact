from emporio.llm import FakeLLM, LLMMessage, MessageRole
from emporio.policy_source import TextPolicyRetriever
from emporio.policy_runtime import PolicyGroundedLLM, runtime_llm_and_tools
from emporio.service import PolicyService


def test_llm_receives_policy_evidence_before_answering() -> None:
    delegate = FakeLLM([FakeLLM.response("A resposta segue a política.")])
    policy = PolicyService(
        TextPolicyRetriever.from_text("Entrega para fora de Campo Grande: PAC em 5 a 12 dias.")
    )
    grounded = PolicyGroundedLLM(delegate, policy)

    result = grounded.complete((LLMMessage(MessageRole.USER, "Qual o prazo de PAC?"),))

    assert result.message.content == "A resposta segue a política."
    system = delegate.calls[0][0]
    assert system.role == MessageRole.SYSTEM
    assert "PAC em 5 a 12 dias" in system.content
    assert "Não invente regras" in system.content


def test_runtime_registers_policy_tool(monkeypatch) -> None:
    policy = PolicyService(TextPolicyRetriever.from_text("PIX tem 5% de desconto."))
    monkeypatch.setattr("emporio.policy_runtime.runtime_policy", lambda: policy)

    llm, tools, registered = runtime_llm_and_tools(FakeLLM())

    assert isinstance(llm, PolicyGroundedLLM)
    assert registered is policy
    assert "answer_policy" in tools.names()


def test_local_model_does_not_receive_tools_by_default(monkeypatch) -> None:
    class LocalFake(FakeLLM):
        provider = "local-llama"

        def __init__(self):
            super().__init__([FakeLLM.response("resposta")])
            self.received_tools = None

        def complete(self, messages, *, tools=()):
            self.received_tools = tools
            return super().complete(messages, tools=tools)

    monkeypatch.delenv("EMPORIO_LLAMA_ENABLE_TOOLS", raising=False)
    delegate = LocalFake()
    policy = PolicyService(TextPolicyRetriever.from_text("Frete PAC: 5 a 12 dias."))

    PolicyGroundedLLM(delegate, policy).complete(
        (LLMMessage(MessageRole.USER, "Qual o prazo do PAC?"),),
        tools=({"type": "function"},),
    )

    assert delegate.received_tools == ()
