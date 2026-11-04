import pytest

from emporio.catalog_service import CatalogService
from emporio.catalog_sqlite import SQLiteCatalogRepository
from emporio.conversation import ConversationService
from emporio.llm import FakeLLM
from emporio.payment_service import PaymentService
from emporio.policy_runtime import PolicyGroundedLLM
from emporio.session_service import SessionService
from emporio.session_sqlite import SQLiteSessionRepository
from emporio.tools import ToolRegistry, ToolValidationError
from test_catalog import row, write_csv, write_categories


def app(tmp_path, price='2500.00'):
    products, categories = tmp_path / 'products.csv', tmp_path / 'categories.csv'
    write_csv(products, [row('89', 'Piano AB-42', price)])
    write_categories(categories, [{'category_id': '1', 'name': 'Pianos', 'description': ''}])
    repo = SQLiteCatalogRepository.connect(tmp_path / 'catalog.db')
    repo.ingest(products, categories)
    tools = ToolRegistry({'catalog': CatalogService(repo), 'payment': PaymentService(repo)})
    sessions = SessionService(SQLiteSessionRepository.connect(tmp_path / 'sessions.db'))
    return ConversationService(sessions, PolicyGroundedLLM(FakeLLM(), None), tools), tools


def test_combination_is_based_on_verified_product_and_labeled(tmp_path):
    service, _ = app(tmp_path)
    result = service.respond('Posso combinar PIX e cartão para o AB-42?')
    assert result.tool_calls == 2
    assert 'Simulação' in result.text and 'R$ 500,00' in result.text
    assert 'R$ 2.000,00' in result.text and '12x' in result.text


@pytest.mark.parametrize('price,expected', [('500.00', 'R$ 35,00'), ('500.01', 'R$ 0,00')])
def test_local_shipping_boundary(tmp_path, price, expected):
    service, _ = app(tmp_path, price)
    result = service.respond('Qual o frete do AB-42 para Campo Grande?')
    assert result.tool_calls == 2
    assert 'simula' in result.text.lower() and expected in result.text


def test_remote_missing_package_does_not_invent_quote(tmp_path):
    service, _ = app(tmp_path)
    result = service.respond('Frete do AB-42 para São Paulo CEP 01001-000')
    assert 'dimensões' in result.text and 'R$' not in result.text


def test_ineligible_combination_and_tool_validation(tmp_path):
    service, tools = app(tmp_path, '2000.00')
    result = service.respond('Combinar PIX e cartão no AB-42')
    assert 'indisponível' in result.text
    with pytest.raises(ToolValidationError):
        tools.execute('analyze_shipping', {'product_id': True, 'destination': 'Campo Grande'})
