import json

from emporio.catalog_service import CatalogService
from emporio.catalog_sqlite import SQLiteCatalogRepository
from emporio.conversation import ConversationService
from emporio.llm import FakeLLM
from emporio.payment_service import PaymentService
from emporio.policy_runtime import PolicyGroundedLLM
from emporio.policy_source import TextPolicyRetriever
from emporio.query_routing import operational_query, has_model_reference
from emporio.service import PolicyService
from emporio.session_service import SessionService
from emporio.session_sqlite import SQLiteSessionRepository
from emporio.tools import ToolRegistry
from test_catalog import row, write_csv, write_categories
from emporio.llm import LLMError
import pytest


QUESTION = 'Quero um Shelby SN-100 Folk Aço Preto, quais as condições de pagamento'


def test_payment_reference_does_not_depend_on_brand_list():
    assert operational_query(QUESTION)
    assert operational_query('Quero um MarcaNova AB-42, como pagar?')
    assert has_model_reference('AB-42')
    assert not has_model_reference('R$ 1000')


@pytest.mark.parametrize('timeout', [False, True])
def test_payment_resolves_product_then_calculates_with_catalog_id(tmp_path, timeout):
    products = tmp_path / 'products.csv'
    categories = tmp_path / 'categories.csv'
    write_csv(products, [row('89', 'Shelby SN-100 Folk Aço Preto', '549.00')])
    write_categories(categories, [{'category_id': '1', 'name': 'Violões', 'description': ''}])
    repository = SQLiteCatalogRepository.connect(tmp_path / 'catalog.db')
    repository.ingest(products, categories)
    policy = PolicyService(TextPolicyRetriever.from_text(
        'Formas de pagamento: PIX, cartão de débito, crédito e boleto. '
        'PIX tem 5% de desconto. Parcelamento conforme valor mínimo.\n---\n'
        'SENTINEL_PRIVATE regras de privacidade.'
    ))

    class Recording(FakeLLM):
        def __init__(self):
            super().__init__([
                FakeLLM.response('Até 12x sem juros e 5% em qualquer pagamento a vista.'),
            ])
            self.advertised = []

        def complete(self, messages, *, tools=()):
            self.advertised.append([s['function']['name'] for s in tools])
            if timeout:
                self.calls.append(tuple(messages))
                raise LLMError('simulated provider timeout')
            return super().complete(messages, tools=tools)

    delegate = Recording()
    tools = ToolRegistry({'catalog': CatalogService(repository), 'payment': PaymentService(repository), 'policy': policy})
    sessions = SessionService(SQLiteSessionRepository.connect(tmp_path / 'sessions.db'))
    context = sessions.create_session()
    for _ in range(6):
        sessions.append_message(context.session_id, 'user', 'old unrelated question')
        sessions.append_message(context.session_id, 'assistant', 'UNRELATED_HISTORY ' * 80)
    result = ConversationService(sessions, PolicyGroundedLLM(delegate, policy), tools).respond(
        QUESTION, session_id=context.session_id)

    assert result.outcome == ('partial' if timeout else 'success')
    assert result.tool_calls == 2
    assert delegate.advertised == [[]]
    assert [len(call) for call in delegate.calls] == [6]
    assert 'UNRELATED_HISTORY' not in ''.join(m.content for m in delegate.calls[0])
    assert 'SENTINEL_PRIVATE' not in delegate.calls[0][0].content
    payment = json.loads(delegate.calls[0][-1].content)['value']
    assert payment['product_id'] == 89
    assert payment['pix_price_brl'] == '521.55'
    assert payment['maximum_installments'] == 6
    assert [p['count'] for p in payment['installments']] == [1, 2, 3, 4, 5, 6]
    assert payment['installments'][-1]['amount_brl'] == '91.50'
    assert result.catalog['products'][0]['product_id'] == 89
    assert '12x' not in result.text
    assert '6x' in result.text
    assert '521,55' in result.text
    assert '91,50' in result.text
