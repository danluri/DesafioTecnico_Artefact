import pytest

from emporio.catalog_service import CatalogService
from emporio.catalog_sqlite import SQLiteCatalogRepository
from emporio.conversation import ConversationService
from emporio.llm import FakeLLM
from emporio.payment_service import PaymentService
from emporio.policy_runtime import PolicyGroundedLLM
from emporio.policy_source import TextPolicyRetriever
from emporio.service import PolicyService
from emporio.session_service import SessionService
from emporio.session_sqlite import SQLiteSessionRepository
from emporio.tools import ToolRegistry
from test_catalog import row, write_csv, write_categories


def setup(tmp_path, multiple=False):
    products, categories = tmp_path / 'products.csv', tmp_path / 'categories.csv'
    rows = [row('89', 'Shelby SN-100 Folk Aço Preto', '549.00')]
    if multiple:
        rows.append(row('90', 'Shelby SN-100 Natural', '600.00'))
    write_csv(products, rows)
    write_categories(categories, [{'category_id': '1', 'name': 'Violões', 'description': ''}])
    repo = SQLiteCatalogRepository.connect(tmp_path / 'catalog.db')
    repo.ingest(products, categories)
    policy = PolicyService(TextPolicyRetriever.from_text('Pagamento: PIX, débito, boleto e cartão sem juros.'))
    tools = ToolRegistry({'catalog': CatalogService(repo), 'payment': PaymentService(repo), 'policy': policy})

    def application(llm):
        sessions = SessionService(SQLiteSessionRepository.connect(tmp_path / 'sessions.db'))
        return ConversationService(sessions, PolicyGroundedLLM(llm, policy), tools)
    return application


@pytest.mark.parametrize('followup', ['Quais as condições de pagamento desse produto?', 'E no PIX?', 'Posso parcelar?'])
def test_price_then_payment_uses_persisted_catalog_selection(tmp_path, followup):
    application = setup(tmp_path)
    first = application(FakeLLM([
        FakeLLM.tool_call('search_catalog', {'name': 'Shelby SN-100'}),
        FakeLLM.response('O Shelby custa R$ 549,00.'),
    ])).respond('Quanto custa o Shelby SN-100 Folk Aço Preto?')
    # Recreate service and LLM: selection must come from this session's persisted data.
    delegate = FakeLLM([FakeLLM.response('Até 12x sem juros.')])
    result = application(delegate).respond(followup, session_id=first.session_id)
    assert result.outcome == 'success'
    assert result.tool_calls == 2
    assert result.catalog['products'][0]['product_id'] == 89
    assert '521,55' in result.text
    assert '6x' in result.text
    assert len(delegate.calls) == 1
    assert len(delegate.calls[0]) == 6  # Current turn plus its two complete tool exchanges.


def test_ambiguous_list_does_not_choose_a_product(tmp_path):
    application = setup(tmp_path, multiple=True)
    first = application(FakeLLM([
        FakeLLM.tool_call('search_catalog', {'name': 'Shelby SN-100'}),
        FakeLLM.response('Encontrei dois modelos.'),
    ])).respond('Quanto custa o Shelby SN-100?')
    delegate = FakeLLM()
    result = application(delegate).respond('Quais as condições de pagamento desse produto?', session_id=first.session_id)
    assert result.tool_calls == 0
    assert 'qual produto' in result.text
    assert delegate.calls == []


def test_new_session_does_not_reuse_other_sessions_product(tmp_path):
    application = setup(tmp_path)
    application(FakeLLM([
        FakeLLM.tool_call('search_catalog', {'name': 'Shelby SN-100'}), FakeLLM.response('R$ 549,00.'),
    ])).respond('Quanto custa o Shelby SN-100?')
    delegate = FakeLLM()
    result = application(delegate).respond('Quais as condições de pagamento desse produto?')
    assert result.tool_calls == 0
    assert 'qual produto' in result.text
    assert delegate.calls == []
