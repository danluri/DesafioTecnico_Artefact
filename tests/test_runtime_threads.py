from emporio.catalog_service import CatalogService
from emporio.catalog_sqlite import SQLiteCatalogRepository
from emporio.conversation import ConversationService
from emporio.dev_console import DevConsoleApplication, create_server
from emporio.llm import FakeLLM
from emporio.session_service import SessionService
from emporio.session_sqlite import SQLiteSessionRepository
from emporio.tools import ToolRegistry
from test_catalog import row, write_csv, write_categories
from test_dev_console import request
import threading
from emporio.llm import LLMError


def test_http_request_executes_catalog_tool_and_persists_session(tmp_path):
    source = tmp_path / 'products.csv'
    write_csv(source, [row('1', 'Violao teste', '900.00')])
    catalog = SQLiteCatalogRepository.connect(tmp_path / 'catalog.db')
    categories = tmp_path / 'categories.csv'
    write_categories(categories, [{'category_id': '1', 'name': 'Violões', 'description': ''}])
    catalog.ingest(source, categories)
    tools = ToolRegistry({'catalog': CatalogService(catalog)})
    llm = FakeLLM([
        FakeLLM.tool_call('search_catalog', {'maximum_budget': '1000'}),
        FakeLLM.response('Violao teste custa R$ 900,00.'),
        FakeLLM.response('Posso ajudar com outra duvida.'),
    ])
    sessions = SessionService(SQLiteSessionRepository.connect(tmp_path / 'sessions.db'))
    app = DevConsoleApplication(ConversationService(sessions, llm, tools), str(tmp_path / 'events.db'))
    server = create_server(app, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, body = request(server.server_address[1], '/api/messages', {
            'message_id': 'thread-test', 'text': 'Violao ate 1000',
        })
        assert status == 200
        assert body['outcome'] == 'success'
        assert body['tool_calls'] == 1
        assert body['persistence'] == 'persisted'
        assert '900.00' in llm.calls[1][-1].content
        assert body['response'] == 'Violao teste custa R$ 900,00.'
        assert body['catalog']['total'] == 1
        assert body['catalog']['products'] == [{
            'product_id': 1, 'name': 'Violao teste', 'price_brl': '900.00',
            'stock_quantity': 2, 'category_name': 'Violões',
        }]
        status, followup = request(server.server_address[1], '/api/messages', {
            'message_id': 'thread-followup', 'text': 'Obrigado', 'session_id': body['session_id'],
        })
        assert status == 200
        assert followup['catalog'] is None
    finally:
        server.shutdown()
        server.server_close()


def test_catalog_table_survives_final_llm_failure(tmp_path):
    class FailsAfterTool(FakeLLM):
        def complete(self, messages, *, tools=()):
            if any(message.role.value == 'tool' for message in messages):
                raise LLMError('provider timeout')
            return FakeLLM.tool_call('search_catalog', {'maximum_budget': '1000'})

    source = tmp_path / 'products.csv'
    write_csv(source, [row('1', 'Violao teste', '900.00')])
    catalog = SQLiteCatalogRepository.connect(tmp_path / 'catalog.db')
    categories = tmp_path / 'categories.csv'
    write_categories(categories, [{'category_id': '1', 'name': 'Violões', 'description': ''}])
    catalog.ingest(source, categories)
    sessions = SessionService(SQLiteSessionRepository.connect(tmp_path / 'sessions.db'))
    app = DevConsoleApplication(ConversationService(
        sessions, FailsAfterTool(), ToolRegistry({'catalog': CatalogService(catalog)})
    ), str(tmp_path / 'events.db'))
    _, result = app.message({'message_id': 'failed-summary', 'text': 'Violao ate 1000'})
    assert result['outcome'] == 'provider_failure'
    assert result['tool_calls'] == 1
    assert result['catalog']['total'] == 1
    assert result['catalog']['products'][0]['price_brl'] == '900.00'
    assert result['persistence'] == 'persisted'
