from concurrent.futures import ThreadPoolExecutor
import json
import logging
import threading
import time

import pytest

from emporio.conversation import ConversationService
from emporio.dev_console import DevConsoleApplication, create_server
from emporio.llm import FakeLLM
from emporio.policy_runtime import PolicyGroundedLLM
from emporio.policy_source import TextPolicyRetriever
from emporio.service import PolicyService
from emporio.session_service import SessionService
from emporio.session_sqlite import SQLiteSessionRepository
from emporio.tools import ToolRegistry, ToolSpec
from emporio.tracing import TraceStore, diagnostic, event, trace_id
from test_dev_console import request


@pytest.fixture
def traced(tmp_path, monkeypatch):
    monkeypatch.setenv('EMPORIO_TRACE_ENABLED', 'true')
    monkeypatch.setenv('EMPORIO_TRACE_DB', str(tmp_path / 'traces.db'))
    monkeypatch.setenv('EMPORIO_RUNTIME_LOG', str(tmp_path / 'runtime.log'))
    logger = logging.getLogger('emporio.local_llama')
    previous = list(logger.handlers)
    logger.handlers.clear()
    yield tmp_path
    for handler in logger.handlers:
        handler.close()
    logger.handlers[:] = previous


def service(path, llm=None, tools=None):
    return ConversationService(SessionService(SQLiteSessionRepository.connect(path / 'sessions.db')),
                               llm or FakeLLM([FakeLLM.response('ok')]), tools or ToolRegistry())


def test_trace_persists_correlates_and_masks_inputs(traced):
    tools = ToolRegistry()
    worker_ids = []
    def worker():
        worker_ids.append(trace_id())
        event('worker_executed')
        return 'public result'
    tools.register(ToolSpec('check_worker', 'Check thread context', {}, (), worker))
    app = service(traced, FakeLLM([FakeLLM.tool_call('check_worker', {}), FakeLLM.response('ok')]), tools)
    outcome = app.respond('PRIVATE customer@example.com 5511999999999', message_id='private-message-id')
    assert outcome.correlation_id == outcome.trace['trace_id'] == worker_ids[0]
    persisted = TraceStore().get(outcome.correlation_id)
    assert persisted['outcome'] == 'success'
    stages = [e['stage'] for e in persisted['events']]
    assert stages[0] == 'message_received'
    assert stages[-1] == 'response_ready'
    assert 'worker_executed' in stages
    assert TraceStore().by_message('private-message-id')['trace_id'] == outcome.correlation_id
    text = json.dumps(persisted) + (traced / 'runtime.log').read_text(encoding='utf-8')
    assert all(secret not in text for secret in ['PRIVATE', 'customer@example.com', '5511999999999', 'private-message-id'])
    assert TraceStore().metrics()['outcomes']['success'] == 1
    for line in (traced / 'runtime.log').read_text(encoding='utf-8').splitlines():
        assert json.loads(line)['trace_id'] == outcome.correlation_id


def test_rag_trace_records_source_and_prompt_version(traced):
    policy = PolicyService(TextPolicyRetriever.from_text('Endereço: Rua Exemplo, 123.'))
    llm = PolicyGroundedLLM(FakeLLM([FakeLLM.response('Rua Exemplo, 123.')]), policy)
    result = service(traced, llm).respond('Qual o endereço da loja?')
    rag = next(e for e in result.trace['events'] if e['stage'] == 'rag')
    assert rag['data']['sources'][0]['page'] == 1
    assert rag['data']['sources'][0]['excerpt_sha256']
    assert result.diagnostics['policy_evidence_available']
    assert next(e for e in result.trace['events'] if e['stage'] == 'routing')['data']['prompt_version']


def test_concurrent_request_diagnostics_do_not_mix(traced):
    barrier = threading.Barrier(2)
    class Concurrent(FakeLLM):
        def complete(self, messages, *, tools=()):
            text = messages[-1].content
            diagnostic(provider_error='TimeoutError' if text == 'first' else None)
            barrier.wait(timeout=5)
            return FakeLLM.response('ok')
    app = service(traced, Concurrent())
    with ThreadPoolExecutor(2) as pool:
        a = pool.submit(app.respond, 'first')
        b = pool.submit(app.respond, 'second')
        first, second = a.result(), b.result()
    assert first.trace['trace_id'] != second.trace['trace_id']
    assert first.diagnostics['provider_error'] == 'TimeoutError'
    assert second.diagnostics['provider_error'] is None


def test_trace_is_readable_while_http_message_is_processing(traced):
    entered, release = threading.Event(), threading.Event()
    class Waiting(FakeLLM):
        def complete(self, messages, *, tools=()):
            event('llm_started')
            entered.set()
            release.wait(5)
            return FakeLLM.response('ok')
    server = create_server(DevConsoleApplication(service(traced, Waiting()), str(traced / 'events.db')), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        with ThreadPoolExecutor(1) as pool:
            response = pool.submit(request, port, '/api/messages', {'message_id': 'live-id', 'text': 'hello'})
            assert entered.wait(5)
            code, trace = request(port, '/api/traces/by-message/live-id')
            assert code == 200 and trace['outcome'] == 'processing'
            assert any(e['stage'] == 'llm_started' for e in trace['events'])
            release.set()
            code, body = response.result()
        assert code == 200
        assert body['trace_id'] == trace['trace_id']
        assert request(port, '/api/traces/' + trace['trace_id'])[1]['outcome'] == 'success'
        assert request(port, '/api/metrics')[1]['sample_size'] == 1
        assert request(port, '/api/traces/invalid')[0] == 400
    finally:
        release.set()
        server.shutdown()
        server.server_close()


def test_retention_and_storage_failure_do_not_break_assistant(traced, monkeypatch):
    first = service(traced).respond('hello')
    store = TraceStore()
    with store.connect() as db:
        db.execute('UPDATE traces SET started=? WHERE trace_id=?', (time.time()-10*86400, first.correlation_id))
    second = service(traced).respond('hello')
    assert store.get(first.correlation_id) is None
    assert store.get(second.correlation_id)
    monkeypatch.setenv('EMPORIO_TRACE_DB', str(traced))  # Directory is not a SQLite file.
    assert service(traced).respond('hello').outcome == 'success'


def test_llm_metrics_and_http_errors_are_correlated_without_raw_error_body(traced, monkeypatch):
    from io import BytesIO
    from urllib.error import HTTPError
    from emporio.llm_local import LocalLlamaLLM

    class Reply:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self):
            return json.dumps({'message': {'content': 'ok'}, 'prompt_eval_count': 20,
                               'eval_count': 3, 'prompt_eval_duration': 1000000}).encode()

    monkeypatch.setattr('emporio.llm_local.urlopen', lambda *a, **kw: Reply())
    good = service(traced, LocalLlamaLLM()).respond('PRIVATE input')
    metric = next(e for e in good.trace['events'] if e['stage'] == 'llm_completed')
    assert metric['data']['prompt_tokens'] == 20
    assert metric['data']['prompt_ms'] == 1

    def rejected(*args, **kwargs):
        raise HTTPError('http://localhost', 400, 'bad request', {}, BytesIO(b'PRIVATE customer payload'))
    monkeypatch.setattr('emporio.llm_local.urlopen', rejected)
    bad = service(traced, LocalLlamaLLM()).respond('PRIVATE input')
    assert bad.outcome == 'provider_failure'
    assert bad.diagnostics['provider_error'] == 'HTTPError:400'
    assert next(e for e in bad.trace['events'] if e['stage'] == 'llm_error')['data']['http_status'] == 400
    assert (traced / 'runtime.log').exists(), getattr(logging.getLogger('emporio.local_llama'), '_emporio_file_error', 'no log handler')
    assert 'PRIVATE' not in (traced / 'runtime.log').read_text(encoding='utf-8')


def test_disabling_history_keeps_request_diagnostics(traced, monkeypatch):
    monkeypatch.setenv('EMPORIO_TRACE_ENABLED', 'false')
    class Diagnosed(FakeLLM):
        def complete(self, messages, *, tools=()):
            diagnostic(provider_error='TimeoutError')
            return FakeLLM.response('ok')
    result = service(traced, Diagnosed()).respond('hello')
    assert result.trace is None
    assert result.diagnostics['provider_error'] == 'TimeoutError'
    assert TraceStore().recent() == []
