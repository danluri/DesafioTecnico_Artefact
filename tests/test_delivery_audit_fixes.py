import pytest

from emporio.dev_console import create_server
from emporio.llm import FakeLLM, LLMMessage
from emporio.policy_runtime import PolicyGroundedLLM, _is_outside_campo_grande_query
from emporio.policy_source import TextPolicyRetriever
from emporio.service import PolicyService


def test_container_binding_requires_explicit_flag(monkeypatch):
    monkeypatch.delenv('EMPORIO_DEV_CONSOLE_ALLOW_CONTAINER_BIND', raising=False)
    with pytest.raises(ValueError):
        create_server(object(), host='0.0.0.0', port=0)
    monkeypatch.setenv('EMPORIO_DEV_CONSOLE_ALLOW_CONTAINER_BIND', 'true')
    server = create_server(object(), host='0.0.0.0', port=0)
    server.server_close()


def test_policy_context_clarifies_exact_500():
    delegate = FakeLLM([FakeLLM.response('O frete é R$ 35,00.')])
    policy = PolicyService(TextPolicyRetriever.from_text('Frete grátis acima de R$ 500.'))
    PolicyGroundedLLM(delegate, policy).complete((LLMMessage('user', 'Frete em Campo Grande para pedido de R$ 500?'),))
    assert 'inclusive exatamente R$ 500,00' in delegate.calls[0][0].content
    assert _is_outside_campo_grande_query('frete fora de Campo Grande')


def test_accessories_are_not_sold_when_manual_confirms_scope():
    policy = PolicyService(TextPolicyRetriever.from_text('Trabalhamos com instrumentos musicais — não comercializamos acessórios como palhetas, cabos e pedais.'))
    result = PolicyGroundedLLM(FakeLLM([FakeLLM.response('Sim, vendemos palhetas.')]), policy).complete(
        (LLMMessage('user', 'Vocês vendem palhetas para guitarra?'),))
    assert 'não vendemos acessórios' in result.message.content


def test_return_answer_rejects_invented_contact_and_reason():
    text = ('Direito de arrependimento para compras online em até 7 dias corridos. '
            'Produto em embalagem original, sem sinais de uso, acessórios e manuais. '
            'O reembolso será realizado na mesma forma de pagamento em até 10 dias úteis. '
            'O frete de devolução é por conta da loja.')
    delegate = FakeLLM([FakeLLM.response('Envie uma foto para info@example.com e justifique o motivo.')])
    result = PolicyGroundedLLM(delegate, PolicyService(TextPolicyRetriever.from_text(text))).complete(
        (LLMMessage('user', 'Me arrependi da compra online, posso devolver?'),))
    assert '7 dias' in result.message.content
    assert 'info@example.com' not in result.message.content
    assert 'justifique' not in result.message.content
