import pytest

from emporio.catalog_service import CatalogService
from emporio.catalog_sqlite import SQLiteCatalogRepository
from test_catalog import row, write_csv, write_categories


@pytest.fixture
def service(tmp_path):
    products = tmp_path / 'products.csv'
    categories = tmp_path / 'categories.csv'
    write_categories(categories, [{'category_id': '1', 'name': 'Violões', 'description': ''}])
    write_csv(products, [
        row('1', 'Yamaha C40', '599.90'),
        row('2', 'Tagima Aço', '899.00'),
        row('3', 'Yamaha Premium', '1500.00'),
        row('4', 'Yamaha Indisponivel', '500.00', stock='0'),
    ])
    repository = SQLiteCatalogRepository.connect(tmp_path / 'catalog.db')
    repository.ingest(products, categories)
    return CatalogService(repository)


@pytest.mark.parametrize('criteria', [
    {'name': 'violão', 'category': 'violão'},
    {'name': 'violões'}, {'name': 'violoes'},
    {'category': 'violaos'}, {'category': 'VIOLÕES'},
])
def test_generic_instrument_selects_category_with_budget_and_stock(service, criteria):
    result = service.search(maximum_budget='1000', **criteria)
    assert result.total == 2
    assert {p.product_id for p in result.products} == {1, 2}


def test_specific_model_name_remains_a_filter(service):
    result = service.search(name='Yamaha', category='violao', maximum_budget='1000')
    assert [p.product_id for p in result.products] == [1]


def test_model_name_search_is_accent_insensitive(service):
    assert [p.product_id for p in service.search(name='tagima aco').products] == [2]


def test_unknown_model_is_not_broadened_to_whole_category(service):
    assert service.search(name='Modelo inexistente', category='violao').total == 0


@pytest.mark.parametrize('budget', ['', ' ', None])
def test_missing_budget_does_not_fail_or_limit_search(service, budget):
    result = service.search(category='violao', maximum_budget=budget)
    assert result.total == 3


@pytest.mark.parametrize('budget', ['R$ 1.000,00', 'R$1000', '1.000', '1000.00'])
def test_currency_formats_preserve_budget(service, budget):
    assert service.search(category='violao', maximum_budget=budget).total == 2


def test_user_query_prevents_invented_category_and_budget():
    from emporio.catalog_search import grounded_search_arguments
    args = grounded_search_arguments('Quais opções de violões disponíveis', {
        'category': 'violin', 'name': 'violão', 'maximum_budget': '1000,00',
    })
    assert args == {'category': 'Violões'}
    assert grounded_search_arguments('Quais violões disponíveis', {
        'category': 'violões', 'name': 'violas',
    }) == {'category': 'Violões'}
    assert grounded_search_arguments('Quais violões Yamaha C40 disponíveis', {
        'category': 'violao', 'name': 'violão Yamaha C40',
    }) == {'category': 'Violões', 'name': 'Yamaha C40'}
    args = grounded_search_arguments('Quais violões até R$1000?', {
        'category': 'violin', 'maximum_budget': '',
    })
    assert args == {'category': 'Violões', 'maximum_budget': '1000'}


def test_tool_keeps_prices_and_stock_without_repeating_full_product_records(service):
    from emporio.tools import ToolRegistry
    tool = ToolRegistry({'catalog': service})
    result = tool.execute('search_catalog', {
        'name': 'violao', 'category': 'violao', 'maximum_budget': '1000',
    }).value
    assert result['total'] == 2
    assert result['products'][0]['price_brl'] in {'599.90', '899.00'}
    assert all(p['stock_quantity'] > 0 for p in result['products'])
    assert 'specs' not in result['products'][0]
    assert result['snapshot']['data_as_of']
