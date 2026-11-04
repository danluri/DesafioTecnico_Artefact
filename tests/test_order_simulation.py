import json
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
import threading

import pytest

from emporio.catalog_service import CatalogService
from emporio.catalog_sqlite import SQLiteCatalogRepository
from emporio.conversation import ConversationService
from emporio.correios import validate_tracking_code
from emporio.dev_console import DevConsoleApplication, create_server
from emporio.llm import FakeLLM, LLMError
from emporio.llm_local import LocalLlamaLLM
from emporio.order import AuthorizedPrincipal
from emporio.order_simulation import OrderSimulation, SimulationError
from emporio.policy_runtime import PolicyGroundedLLM, runtime_llm_and_tools
from emporio.session_service import SessionService
from emporio.session_sqlite import SQLiteSessionRepository
from emporio.tools import ToolRegistry, ToolAuthorizationError
from emporio.tracing import TraceStore
from test_catalog import row, write_csv, write_categories


@pytest.fixture
def setup(tmp_path, monkeypatch):
    def no_carrier_calls(*args, **kwargs):
        raise AssertionError('Simulation must not call real Correios')
    monkeypatch.setattr('emporio.correios.urlopen', no_carrier_calls)
    monkeypatch.setenv('EMPORIO_TRACE_DB', str(tmp_path / 'traces.db'))
    monkeypatch.setenv('EMPORIO_RUNTIME_LOG', str(tmp_path / 'runtime.log'))
    source, categories = tmp_path / 'products.csv', tmp_path / 'categories.csv'
    write_csv(source, [row('89', 'Shelby SN-100', '549.00')])
    write_categories(categories, [{'category_id': '1', 'name': 'Violões', 'description': ''}])
    catalog = SQLiteCatalogRepository.connect(tmp_path / 'catalog.db')
    catalog.ingest(source, categories)
    simulator = OrderSimulation(tmp_path / 'sim.db', catalog)
    sessions = SessionService(SQLiteSessionRepository.connect(tmp_path / 'sessions.db'))
    tools = ToolRegistry({'order': simulator, 'catalog': CatalogService(catalog)})
    llm = PolicyGroundedLLM(FakeLLM([FakeLLM.response('Inventei AB123456789BR')]*10), None)
    conversation = ConversationService(sessions, llm, tools)
    app = DevConsoleApplication(conversation, str(tmp_path / 'whatsapp.db'))
    return app, simulator, catalog


def create(app):
    status, identity = app.simulation('/api/simulation/start', {})
    assert status == 200
    payload = {'product_id': 89, 'quantity': 1, 'payment_method': 'pix', 'request_id': 'create-1'}
    status, result = app.simulation('/api/simulation/orders', payload, identity['token'])
    assert status == 200
    return identity, result['order'], payload


def test_lifecycle_is_persistent_idempotent_and_does_not_reserve_stock(setup, tmp_path):
    app, sim, catalog = setup
    identity, order, payload = create(app)
    client = sim.client(identity['token'])
    reference = order['order_reference']
    assert order['status'] == 'awaiting_payment'
    assert order['tracking'] is None
    assert order['total_brl'] == '521.55'
    assert order['freight_included'] is False
    assert sim.create_order(client, payload) == order
    with pytest.raises(SimulationError) as conflict:
        sim.create_order(client, {**payload, 'quantity': 2})
    assert conflict.value.status == 409
    with pytest.raises(SimulationError) as early:
        sim.transition(client, reference, 'ship')
    assert early.value.status == 409
    paid = sim.transition(client, reference, 'pay')
    assert paid['status'] == 'paid' and paid['tracking'] is None
    assert sim.transition(client, reference, 'pay') == paid
    shipped = sim.transition(client, reference, 'ship')
    code = shipped['tracking']['code']
    validate_tracking_code(code)
    assert shipped['tracking']['source'] == 'Mock Correios'
    assert sim.transition(client, reference, 'ship') == shipped
    assert sim.transition(client, reference, 'pay') == shipped
    assert [e['action'] for e in shipped['events']] == ['created', 'payment_approved', 'dispatched']
    assert 'WhatsApp simulado' == shipped['notification']['channel']
    assert 'Nenhuma mensagem real' in shipped['notification']['message']
    assert catalog.find_by_id(89).stock_quantity == 2
    reopened = OrderSimulation(tmp_path / 'sim.db', catalog)
    assert reopened.list_orders(reopened.client(identity['token'])) == [shipped]
    assert 'token' not in json.dumps(shipped)


def test_foreign_orders_and_identity_claims_are_rejected(setup):
    app, sim, _ = setup
    identity, order, _ = create(app)
    _, other = app.simulation('/api/simulation/start', {})
    assert sim.list_orders(sim.client(other['token'])) == []
    with pytest.raises(SimulationError) as foreign:
        app.simulation('/api/simulation/orders/' + order['order_reference'] + '/pay', {}, other['token'])
    assert foreign.value.status == 403
    with pytest.raises(ToolAuthorizationError):
        app.conversation.tools.execute('order_status', {'order_reference': order['order_reference']})
    with pytest.raises(ToolAuthorizationError):
        app.conversation.tools.execute('order_status', {'order_reference': order['order_reference']},
                                       principal=AuthorizedPrincipal(sim.client(other['token'])['customer_id']))
    with pytest.raises(SimulationError):
        app.message({'text': 'rastreio', 'message_id': 'x', 'session_id': identity['session_id']}, other['token'])
    _, result = app.message({'text': 'Qual o rastreio do pedido ' + order['order_reference'] + '?',
                             'message_id': 'anonymous', 'customer_id': 1})
    assert result['outcome'] == 'unauthorized'
    assert result['tool_calls'] == 1
    assert not set(app.conversation.tools.names()) & {'create_order', 'pay', 'ship'}


@pytest.mark.parametrize('state', ['awaiting_payment', 'paid', 'shipped'])
@pytest.mark.parametrize('timeout', [False, True])
def test_chat_looks_up_owned_order_and_grounds_reply(setup, state, timeout):
    app, sim, _ = setup
    identity, order, _ = create(app)
    client = sim.client(identity['token'])
    if state != 'awaiting_payment':
        order = sim.transition(client, order['order_reference'], 'pay')
    if state == 'shipped':
        order = sim.transition(client, order['order_reference'], 'ship')
    if timeout:
        class Timeout(FakeLLM):
            def complete(self, messages, *, tools=()):
                self.calls.append(tuple(messages))
                raise LLMError('simulated timeout')
        app.conversation.llm.delegate = Timeout()
    _, result = app.message({'text': 'Qual o rastreio do pedido ' + order['order_reference'] + '?',
                             'message_id': 'tracking-1', 'session_id': identity['session_id']}, identity['token'])
    assert result['tool_calls'] == 1
    assert result['persistence'] == 'persisted'
    assert result['outcome'] == 'partial'
    assert 'AB123456789BR' not in result['response']
    assert order['order_reference'] in result['response']
    if state == 'shipped':
        assert order['tracking']['code'] in result['response']
        assert 'Mock Correios' in result['response']
    else:
        assert 'não' in result['response'] and 'rastreio' in result['response']
    assert len(app.conversation.llm.delegate.calls) == 1
    assert 'PEDIDO FICTICIO VERIFICADO' in app.conversation.llm.delegate.calls[0][0].content


def test_create_rejects_unavailable_quantity_and_concurrent_ship_is_stable(setup):
    app, sim, _ = setup
    identity, order, payload = create(app)
    client = sim.client(identity['token'])
    for override in [{'quantity': 3}, {'quantity': True}, {'product_id': 999}, {'product_id': 2**64}, {'payment_method': 'bitcoin'}, {'payment_method': []}]:
        with pytest.raises(SimulationError):
            sim.create_order(client, {**payload, 'request_id': 'invalid', **override})
    sim.transition(client, order['order_reference'], 'pay')
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: sim.transition(client, order['order_reference'], 'ship'), range(4)))
    assert len({r['tracking']['code'] for r in results}) == 1
    assert all(len(r['events']) == 3 for r in results)


def test_verified_status_can_be_humanized_by_llm_without_fallback(setup):
    app, sim, _ = setup
    identity, order, _ = create(app)
    client = sim.client(identity['token'])
    sim.transition(client, order['order_reference'], 'pay')
    shipped = sim.transition(client, order['order_reference'], 'ship')
    answer = f"Seu pedido fictício {order['order_reference']} foi despachado! Rastreio: {shipped['tracking']['code']} (Mock Correios)."
    app.conversation.llm.delegate = FakeLLM([FakeLLM.response(answer)])
    _, result = app.message({'text': f"Qual o rastreio do pedido {order['order_reference']}?",
                             'message_id': 'llm-prose', 'session_id': identity['session_id']}, identity['token'])
    assert result['outcome'] == 'success'
    assert result['response'] == answer
    assert result['tool_calls'] == 1


def test_session_replacement_remains_bound_for_next_message(setup, monkeypatch):
    app, sim, _ = setup
    identity, order, _ = create(app)
    sessions = app.conversation.sessions
    original = sessions.get_context
    monkeypatch.setattr(sessions, 'get_context', lambda session_id, principal=None: sessions.create_session(principal))
    payload = {'text': f"Qual o rastreio do pedido {order['order_reference']}?", 'session_id': identity['session_id'], 'message_id': 'recovered-1'}
    _, result = app.message(payload, identity['token'])
    assert result['session_id'] != identity['session_id']
    assert sim.client(identity['token'])['session_id'] == result['session_id']
    monkeypatch.setattr(sessions, 'get_context', original)
    _, following = app.message({**payload, 'message_id': 'recovered-2', 'session_id': result['session_id']}, identity['token'])
    assert following['outcome'] == 'partial' and following['tool_calls'] == 1


def test_correct_tracking_code_does_not_authorize_delivery_promises(setup):
    app, sim, _ = setup
    identity, order, _ = create(app)
    client = sim.client(identity['token'])
    sim.transition(client, order['order_reference'], 'pay')
    shipped = sim.transition(client, order['order_reference'], 'ship')
    answer = f"Pedido fictício {order['order_reference']} despachado. {shipped['tracking']['code']}. Entrega garantida amanhã!"
    app.conversation.llm.delegate = FakeLLM([FakeLLM.response(answer)])
    _, result = app.message({'text': f"Qual o rastreio do pedido {order['order_reference']}?",
                             'message_id': 'invented-delivery', 'session_id': identity['session_id']}, identity['token'])
    assert result['outcome'] == 'partial'
    assert 'amanhã' not in result['response'] and 'garantida' not in result['response']
    assert shipped['tracking']['code'] in result['response']


@pytest.mark.parametrize('body', ['[]', '{"message":null}', '{"message":{"content":"ok"},"load_duration":null}'])
def test_malformed_provider_telemetry_preserves_verified_tracking(setup, monkeypatch, body):
    app, sim, _ = setup
    identity, order, _ = create(app)
    client = sim.client(identity['token'])
    sim.transition(client, order['order_reference'], 'pay')
    shipped = sim.transition(client, order['order_reference'], 'ship')
    class Reply:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return body.encode()
    monkeypatch.setattr('emporio.llm_local.urlopen', lambda *args, **kwargs: Reply())
    app.conversation.llm.delegate = LocalLlamaLLM(model='llama3.1:latest')
    _, result = app.message({'text': f"Qual o rastreio do pedido {order['order_reference']}?",
                             'message_id': 'malformed-provider', 'session_id': identity['session_id']}, identity['token'])
    assert result['outcome'] == 'partial'
    assert shipped['tracking']['code'] in result['response']
    assert result['provider_error'] in {'AttributeError', 'TypeError'}


def test_http_flow_and_audit_traces(setup, monkeypatch, tmp_path):
    app, _, _ = setup
    monkeypatch.setenv('EMPORIO_TRACE_ENABLED', 'true')
    server = create_server(app, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def request(path, payload=None, token=None):
        conn = HTTPConnection('127.0.0.1', server.server_address[1], timeout=5)
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['X-Emporio-Simulation-Token'] = token
        conn.request('GET' if payload is None else 'POST', path,
                     body=json.dumps(payload) if payload is not None else None, headers=headers)
        response = conn.getresponse()
        result = json.loads(response.read())
        conn.close()
        return response.status, result
    try:
        assert request('/api/simulation')[1]['enabled']
        _, identity = request('/api/simulation/start', {})
        token = identity['token']
        assert request('/api/simulation/orders', {'product_id': 89})[0] == 403
        assert request('/api/simulation/orders', [], token)[0] == 400
        _, result = request('/api/simulation/orders', {'product_id': 89, 'request_id': 'http-1'}, token)
        reference = result['order']['order_reference']
        assert request(f'/api/simulation/orders/{reference}/ship', {}, token)[0] == 409
        assert request(f'/api/simulation/orders/{reference}/pay', {}, token)[0] == 200
        _, shipped = request(f'/api/simulation/orders/{reference}/ship', {}, token)
        assert shipped['order']['tracking']['code']
        _, message = request('/api/messages', {'session_id': identity['session_id'], 'message_id': 'http-chat',
                                              'text': f'Qual o rastreio do pedido {reference}?'}, token)
        assert message['tool_calls'] == 1
        assert shipped['order']['tracking']['code'] in message['response']
        trace = TraceStore().get(shipped['trace_id'])
        assert trace['outcome'] == 'action_success'
        assert any(e['stage'] == 'simulation_order' for e in trace['events'])
        assert TraceStore().metrics()['sample_size'] == 1
        assert request('/api/simulation', token=token)[1]['orders'][0]['status'] == 'shipped'
        assert token not in (tmp_path / 'runtime.log').read_text(encoding='utf-8')
        db = app.simulator.connect()
        with db:
            db.execute("UPDATE sim_clients SET expires_at='2000-01-01T00:00:00+00:00'")
        db.close()
        assert request('/api/simulation', token=token)[0] == 403
        assert request(f'/api/simulation/orders/{reference}/pay', {}, token)[0] == 403
        assert request('/api/messages', {'session_id': identity['session_id'], 'message_id': 'expired', 'text': 'rastreio'}, token)[0] == 403
        assert app.simulator.get_status(reference, AuthorizedPrincipal(1))['status'] == 'shipped'
    finally:
        server.shutdown()
        server.server_close()


def test_runtime_simulation_requires_explicit_safe_configuration(setup, tmp_path, monkeypatch):
    app, _, _ = setup
    monkeypatch.delenv('EMPORIO_POLICY_SOURCE', raising=False)
    monkeypatch.setenv('EMPORIO_CATALOG_DB_PATH', str(tmp_path / 'catalog.db'))
    monkeypatch.setenv('EMPORIO_DB_PATH', str(tmp_path / 'runtime.db'))
    monkeypatch.setenv('EMPORIO_DEV_ORDER_DB', str(tmp_path / 'runtime-sim.db'))
    monkeypatch.setenv('EMPORIO_DEV_ORDER_SIMULATION_ENABLED', 'false')
    assert runtime_llm_and_tools(FakeLLM())[1].order_simulator is None
    monkeypatch.setenv('EMPORIO_DEV_ORDER_SIMULATION_ENABLED', 'true')
    llm, tools, policy = runtime_llm_and_tools(FakeLLM())
    assert isinstance(llm, PolicyGroundedLLM) and policy is None
    assert tools.order_simulator is not None and 'order_status' in tools.names()
    monkeypatch.setenv('EMPORIO_DEV_ORDER_DB', str(tmp_path / 'catalog.db'))
    with pytest.raises(ValueError, match='own database'):
        runtime_llm_and_tools(FakeLLM())
    monkeypatch.setenv('EMPORIO_ENV', ' production ')
    with pytest.raises(ValueError, match='development'):
        runtime_llm_and_tools(FakeLLM())
    plain = DevConsoleApplication(ConversationService(app.conversation.sessions, FakeLLM(), ToolRegistry()), str(tmp_path / 'plain.db'))
    assert plain.simulation('/api/simulation')[1] == {'enabled': False}
    assert plain.simulation('/api/simulation/start', {})[0] == 404


def test_post_sale_is_owned_idempotent_and_visible_in_chat(setup, tmp_path):
    app, sim, catalog = setup
    identity, order, _ = create(app)
    _, other = app.simulation('/api/simulation/start', {})
    reference = order['order_reference']
    path = f'/api/simulation/orders/{reference}/complaint'
    payload = {'description': 'Produto danificado', 'request_id': 'case-1'}
    with pytest.raises(SimulationError):
        app.simulation(path, payload, other['token'])
    with pytest.raises(SimulationError):
        app.simulation(path, payload)
    _, first = app.simulation(path, payload, identity['token'])
    _, retry = app.simulation(path, payload, identity['token'])
    assert first['post_sale'] == retry['post_sale']
    with pytest.raises(SimulationError) as conflict:
        app.simulation(path, {**payload, 'description': 'outro'}, identity['token'])
    assert conflict.value.status == 409
    return_path = f'/api/simulation/orders/{reference}/return'
    return_payload = {'description': 'Arrependimento', 'request_id': 'case-2'}
    _, created = app.simulation(return_path, return_payload, identity['token'])
    simulated_return = created['post_sale'][-1]
    assert simulated_return['return_code'].startswith('DEV-SIM-')
    assert simulated_return['eligibility'] == 'pending'
    assert len(simulated_return['instructions']) == 3
    _, retried = app.simulation(return_path, return_payload, identity['token'])
    assert retried['post_sale'][-1] == simulated_return
    reopened = OrderSimulation(tmp_path / 'sim.db', catalog)
    persisted = reopened.list_orders(reopened.client(identity['token']))[0]['post_sale']
    assert len(persisted) == 2 and persisted[-1] == simulated_return
    _, answer = app.message({'text': f'Minhas reclamações e devolução do pedido {reference}',
                             'message_id': 'cases-chat', 'session_id': identity['session_id']}, identity['token'])
    assert answer['tool_calls'] == 0 and '1 reclamação' in answer['response'] and '1 pedido' in answer['response']
    assert simulated_return['return_code'] in answer['response']
    assert 'Elegibilidade pendente' in answer['response']
    assert all(instruction in answer['response'] for instruction in simulated_return['instructions'])
    assert not app.conversation.llm.delegate.calls
    _, denied = app.message({'text': f'Minhas reclamações do pedido {reference}',
                             'message_id': 'foreign-case', 'session_id': other['session_id']}, other['token'])
    assert denied['outcome'] == 'unauthorized' and '1 reclamação' not in denied['response']
    assert simulated_return['return_code'] not in denied['response']
    assert not set(app.conversation.tools.names()) & {'complaint', 'return', 'create_complaint', 'request_return'}


def test_post_sale_rejects_invalid_content_without_creating_records(setup):
    app, sim, _ = setup
    identity, order, _ = create(app)
    path = f"/api/simulation/orders/{order['order_reference']}/return"
    for description in ('', ' ', 'x' * 501, None):
        with pytest.raises(SimulationError):
            app.simulation(path, {'description': description, 'request_id': 'x'}, identity['token'])
    assert sim.list_orders(sim.client(identity['token']))[0]['post_sale'] == []
