import pytest

from emporio.llm import FakeLLM, LLMMessage
from emporio.policy_runtime import PolicyGroundedLLM, _tools_for_query
from emporio.policy_source import TextPolicyRetriever
from emporio.service import PolicyService
from emporio.query_routing import needs_policy
from emporio.catalog_search import grounded_search_arguments


@pytest.mark.parametrize('question', [
    'Qual o endereço da loja?', 'Onde fica a loja?', 'Qual a localização?',
    'Vocês abrem no domingo?', 'Qual é o telefone?',
    'Como chegar?', 'Qual é o CEP da loja?',
    'Me arrependi da minha compra, posso devolver meu pedido?',
    'Desisti da compra', 'Como solicito reembolso?', 'Quero devolver',
    'Qual a garantia?', 'Como cuidam dos meus dados pessoais?',
    'Quanto custa o frete para São Paulo?',
])
def test_store_and_policy_questions_get_retrieval_without_catalog_tools(question):
    assert needs_policy(question)
    assert _tools_for_query(({'function': {'name': 'search_catalog'}},), question) == ()


@pytest.mark.parametrize('question', [
    'Quais opções de violões disponíveis custando até R$1000?',
    'Quanto custa o Takamine GD20?', 'Qual o preço do Yamaha C40?',
])
def test_product_questions_get_catalog_tool(question):
    assert not needs_policy(question)
    tool = {'function': {'name': 'search_catalog'}}
    assert _tools_for_query((tool,), question) == (tool,)


def test_address_after_catalog_discards_irrelevant_history_but_uses_manual():
    delegate = FakeLLM([FakeLLM.response('Endereco confirmado.')])
    grounded = PolicyGroundedLLM(delegate, PolicyService(TextPolicyRetriever.from_text(
        'Endereço da loja: Rua Exemplo, 123, Centro.\n---\n'
        'Direito de arrependimento: devolução em sete dias nas compras online.'
    )))
    grounded.complete((LLMMessage('user', 'Quais violoes?'),
                       LLMMessage('assistant', 'Lista longa de modelos'),
                       LLMMessage('user', 'Qual o endereço da loja?')))
    sent = delegate.calls[0]
    assert len(sent) == 2
    assert 'Rua Exemplo' in sent[0].content
    assert 'Lista longa' not in sent[0].content
    assert grounded.last_passage_count == 1


def test_arrependimento_retrieves_return_policy():
    delegate = FakeLLM([FakeLLM.response('Consulte as condicoes de devolucao.')])
    grounded = PolicyGroundedLLM(delegate, PolicyService(TextPolicyRetriever.from_text(
        'Política de devolução: compras online, sete dias após o recebimento.'
    )))
    result = grounded.complete((LLMMessage('user', 'Me arrependi da minha compra, posso devolver meu pedido?'),))
    assert 'sete dias' in delegate.calls[0][0].content
    assert grounded.last_passage_count == 1
    assert 'compras online' in result.message.content


def test_price_lookup_does_not_invent_a_budget():
    assert grounded_search_arguments('Quanto custa o Takamine GD20?', {
        'name': 'Takamine GD20', 'maximum_budget': '1000',
    }) == {'name': 'Takamine GD20'}


def test_product_payment_question_keeps_calculation_tool_and_policy():
    question = 'Quanto custa o Yamaha C40 no PIX?'
    assert needs_policy(question)
    tools = tuple({'function': {'name': name}} for name in
                  ('search_catalog', 'product_detail', 'calculate_payment', 'answer_policy'))
    assert [t['function']['name'] for t in _tools_for_query(tools, question)] == [
        'search_catalog', 'calculate_payment',
    ]
