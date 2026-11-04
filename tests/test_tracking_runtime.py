import pytest

from emporio.llm import FakeLLM, LLMMessage, LLMError
from emporio.policy_runtime import PolicyGroundedLLM, _policy_query, _tools_for_query
from emporio.policy_source import TextPolicyRetriever
from emporio.service import PolicyService


QUESTION = 'Vou efetuar o pagamento em pix, me de o rastreio'
EVIDENCE = ('O código de rastreamento é enviado por e-mail e WhatsApp '
            'assim que o pedido é despachado.')


def grounded(delegate):
    return PolicyGroundedLLM(delegate, PolicyService(TextPolicyRetriever.from_text(
        'PIX cartão boleto formas pagamento parcela.\n---\n' + EVIDENCE
    )))


def test_tracking_has_priority_over_payment_and_does_not_inherit_failure_history():
    delegate = FakeLLM([FakeLLM.response('Você já tem o número do pedido? O código chega após o despacho.')])
    llm = grounded(delegate)
    llm.complete((LLMMessage('user', 'Quero Shelby SN-100, como pagar?'),
                  LLMMessage('assistant', 'Não consegui consultar o assistente agora. Tente novamente mais tarde.'),
                  LLMMessage('user', QUESTION)))
    sent = delegate.calls[0]
    assert len(sent) == 2
    assert EVIDENCE in sent[0].content
    assert 'PIX cartão boleto' not in sent[0].content
    assert 'Não consegui consultar' not in sent[0].content
    assert 'rastreamento' in _policy_query(QUESTION)
    assert _tools_for_query(({'function': {'name': 'search_catalog'}},), QUESTION) == ()


@pytest.mark.parametrize('answer', [
    'Não consegui consultar o assistente agora. Tente novamente mais tarde.',
    'Seu rastreio é AB123456789BR.',
    'Seu rastreio é ab123456789br.',
    'Seu pagamento foi confirmado e seu pedido foi despachado.',
    'Qual é o número do pedido? Com isso, posso verificar o código de rastreamento.',
])
def test_unverified_tracking_and_repeated_system_errors_are_not_returned(answer):
    result = grounded(FakeLLM([FakeLLM.response(answer)])).complete((LLMMessage('user', QUESTION),))
    assert 'número do pedido' in result.message.content
    assert 'quando o pedido é despachado' in result.message.content
    assert 'não confirma' in result.message.content
    assert 'AB123456789BR' not in result.message.content
    assert result.usage['grounded_fallback'] == 1


def test_tracking_timeout_returns_safe_policy_guidance():
    class Failing(FakeLLM):
        def complete(self, messages, *, tools=()):
            raise LLMError('provider timeout')
    result = grounded(Failing()).complete((LLMMessage('user', QUESTION),))
    assert 'número do pedido' in result.message.content
    assert result.usage['grounded_fallback'] == 1


def test_generated_system_error_is_not_counted_as_success(tmp_path):
    from emporio.conversation import ConversationService
    from emporio.session_service import SessionService
    from emporio.session_sqlite import SQLiteSessionRepository
    from emporio.tools import ToolRegistry
    app = ConversationService(SessionService(SQLiteSessionRepository.connect(tmp_path / 'sessions.db')),
                              FakeLLM([FakeLLM.response('Não consegui consultar o assistente agora. Tente novamente mais tarde.')]),
                              ToolRegistry())
    assert app.respond('pergunta').outcome == 'answer_failure'
