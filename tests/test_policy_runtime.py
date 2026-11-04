from emporio.llm import FakeLLM, LLMCapabilities, LLMMessage, MessageRole
from emporio.policy_source import TextPolicyRetriever
from emporio.policy_runtime import PolicyGroundedLLM, runtime_llm_and_tools
from emporio.service import PolicyService


def test_llm_receives_policy_evidence_before_answering() -> None:
    delegate = FakeLLM([FakeLLM.response("A resposta segue a politica.")])
    policy = PolicyService(
        TextPolicyRetriever.from_text("Entrega para fora de Campo Grande: PAC em 5 a 12 dias.")
    )
    grounded = PolicyGroundedLLM(delegate, policy)

    result = grounded.complete((LLMMessage(MessageRole.USER, "Qual o prazo de PAC?"),))

    assert result.message.content == "A resposta segue a politica."
    system = delegate.calls[0][0]
    assert system.role == MessageRole.SYSTEM
    assert "PAC em 5 a 12 dias" in system.content
    assert "Nao invente regras" in system.content
    assert "EVIDENCIA DO MANUAL DA LOJA" in system.content
    assert "Entrega para fora" in grounded.last_evidence
    assert "inclusive exatamente R$ 500,00" in grounded.last_evidence


def test_runtime_registers_policy_tool(monkeypatch) -> None:
    policy = PolicyService(TextPolicyRetriever.from_text("PIX tem 5% de desconto."))
    monkeypatch.setattr("emporio.policy_runtime.runtime_policy", lambda: policy)

    llm, tools, registered = runtime_llm_and_tools(FakeLLM())

    assert isinstance(llm, PolicyGroundedLLM)
    assert registered is policy
    assert "answer_policy" in tools.names()


def test_provider_without_tool_calling_capability_does_not_receive_tools(monkeypatch) -> None:
    class LocalFake(FakeLLM):
        provider = "local-llama"
        capabilities = LLMCapabilities(tool_calling=False)

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


def test_external_delivery_query_excludes_local_delivery_rule() -> None:
    policy = PolicyService(
        TextPolicyRetriever.from_text(
            "5.1 Campo Grande: prazo de entrega 1 a 3 dias uteis.\n---\n"
            "5.2 Outras cidades: PAC 5 a 12 dias uteis; SEDEX 2 a 5 dias uteis."
        )
    )
    grounded = PolicyGroundedLLM(FakeLLM([FakeLLM.response("ok")]), policy)

    grounded.complete((LLMMessage(MessageRole.USER, "Qual o prazo para sao paulo?"),))

    assert "PAC 5 a 12" in grounded.last_evidence
    assert "1 a 3 dias" not in grounded.last_evidence


def test_external_delivery_response_cannot_use_local_sla() -> None:
    policy = PolicyService(
        TextPolicyRetriever.from_text(
            "5.1 Campo Grande: prazo de entrega 1 a 3 dias uteis.\n---\n"
            "5.2 Outras cidades: PAC 5 a 12 dias uteis; SEDEX 2 a 5 dias uteis."
        )
    )
    grounded = PolicyGroundedLLM(
        FakeLLM([FakeLLM.response("O prazo é de 1 a 3 dias úteis.")]), policy
    )

    result = grounded.complete(
        (LLMMessage(MessageRole.USER, "Qual o prazo para sao paulo?"),)
    )

    assert "PAC" in result.message.content
    assert "1 a 3" not in result.message.content


def test_local_shipping_500_corrects_model_claim_of_free_shipping() -> None:
    policy = PolicyService(TextPolicyRetriever.from_text('Política de entregas.'))
    llm = PolicyGroundedLLM(FakeLLM([FakeLLM.response('O frete é grátis!')]), policy)
    answer = llm.complete((LLMMessage(MessageRole.USER,
        'Para Campo Grande, quanto é o frete de um pedido de R$ 500,00?'),))
    assert 'R$ 35,00' in answer.message.content
    assert 'somente para pedidos acima' in answer.message.content


def test_local_boundary_does_not_apply_to_other_cities() -> None:
    policy = PolicyService(TextPolicyRetriever.from_text('Frete para outras cidades sob consulta.'))
    llm = PolicyGroundedLLM(FakeLLM([FakeLLM.response('O frete é grátis.')]), policy)
    answer = llm.complete((LLMMessage(MessageRole.USER,
        'Frete de pedido de R$ 500,00 para São Paulo?'),))
    assert 'R$ 35,00' not in answer.message.content


def test_catalog_query_does_not_receive_unrelated_policy_pages() -> None:
    policy = PolicyService(TextPolicyRetriever.from_text("PAC de 5 a 12 dias uteis."))
    grounded = PolicyGroundedLLM(FakeLLM([FakeLLM.response("ok")]), policy)

    grounded.complete((LLMMessage(MessageRole.USER, "Voce tem violao disponivel?"),))

    assert grounded.last_evidence == "Nenhuma politica da loja e necessaria para esta pergunta."
