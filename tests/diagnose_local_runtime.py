"""Manual diagnostic: original prompt, real Ollama and catalog, isolated sessions."""

import json
import os
import sys
import sqlite3
from pathlib import Path
from time import monotonic
from urllib.request import Request, urlopen

from emporio.catalog_service import CatalogService
from emporio.catalog_sqlite import SQLiteCatalogRepository
from emporio.llm import LLMMessage
from emporio.llm_local import LocalLlamaLLM
from emporio.policy_runtime import runtime_llm_and_tools
from emporio.conversation import ConversationService
from emporio.session_service import SessionService
from emporio.session_sqlite import SQLiteSessionRepository


def report(event, **values):
    print(json.dumps({'event': event, **values}, ensure_ascii=True), flush=True)


def main():
    root = Path(__file__).resolve().parents[1]
    pdf = next(root.glob('Desafio*/Desafio*/data/*loja.pdf'))
    os.environ['EMPORIO_POLICY_SOURCE'] = str(pdf)
    os.environ['EMPORIO_POLICY_SEMANTIC_ENABLED'] = 'false'
    os.environ['EMPORIO_CATALOG_DB_PATH'] = str(root / 'data/catalog.db')
    query = 'Quais opções de violões disponíveis custando até R$1000?'
    if '--key-cases' in sys.argv:
        from emporio.llm import FakeLLM
        grounded, tools, _ = runtime_llm_and_tools(FakeLLM())
        from emporio.policy_runtime import _tools_for_query
        for question in [query, 'Qual o endereço da loja?', 'Quanto custa o Takamine GD20?',
                         'Me arrependi da minha compra, posso devolver meu pedido?']:
            report('key_case', query=question, evidence=grounded._evidence(question),
                   tools=[s['function']['name'] for s in _tools_for_query(tools.schemas(), question)])
        return
    if '--address' in sys.argv:
        query = 'Qual o endereço da loja?'
    if '--returns' in sys.argv:
        query = 'Me arrependi da minha compra, posso devolver meu pedido?'
    if '--price' in sys.argv:
        query = 'Quanto custa o Takamine GD20?'
    if '--shelby-payment' in sys.argv:
        query = 'Quero um Shelby SN-100 Folk Aço Preto, quais as condições de pagamento'
    if '--tracking' in sys.argv:
        query = 'Vou efetuar o pagamento em pix, me de o rastreio'
    if '--latest-user' in sys.argv:
        db = sqlite3.connect(root / 'data/emporio-rag.db')
        saved = db.execute("SELECT content FROM session_messages WHERE role='user' ORDER BY created_at DESC LIMIT 1").fetchone()
        db.close()
        if saved:
            query = saved[0]
            report('reproduced_query', query=query)
    if '--history' in sys.argv:
        connection = sqlite3.connect(root / 'data/diagnostic-session.db')
        for (content,) in connection.execute('SELECT content FROM session_messages'):
            if content.startswith('tool '):
                report('saved_tool_result', content=content)
        connection.close()
        return
    catalog = CatalogService(SQLiteCatalogRepository.connect(root / 'data/catalog.db'))
    try:
        result = catalog.search(maximum_budget='1000')
        report('catalog_check', total=result.total, products=[p.name for p in result.products])
    except Exception as exc:
        report('catalog_error', error=type(exc).__name__, detail=str(exc))

    if '--runtime-only' in sys.argv:
        run_runtime(root, query)
        return

    if '--tool-only' in sys.argv:
        llm, tools, _ = runtime_llm_and_tools(LocalLlamaLLM(model='llama3.1:latest', timeout=180))
        response = llm.complete((LLMMessage('user', query),), tools=tools.schemas())
        for call in response.tool_calls:
            report('tool_arguments', name=call.name, arguments=call.arguments)
            try:
                from emporio.catalog_search import grounded_search_arguments
                arguments = grounded_search_arguments(query, dict(call.arguments)) if call.name == 'search_catalog' else call.arguments
                report('validated_tool_arguments', arguments=arguments)
                value = tools.execute(call.name, arguments).value
                report('tool_result', total=value.get('total'))
            except Exception as exc:
                report('tool_error', error=type(exc).__name__, cause=str(exc.__cause__))
        return

    if '--catalog-variants' in sys.argv:
        for criteria in ({'category': 'Violões'}, {'category': 'violões'},
                         {'category': 'violoes'}, {'name': 'violões'}):
            found = catalog.search(maximum_budget='1000', **criteria)
            report('catalog_variant', criteria=criteria, total=found.total)
        return

    class Capture(LocalLlamaLLM):
        def complete(self, messages, *, tools=()):
            self.captured = messages, tools
            from emporio.llm import FakeLLM
            return FakeLLM.response('capture')

    capture = Capture(model='llama3.1:latest')
    grounded, tools, _ = runtime_llm_and_tools(capture)
    grounded.complete((LLMMessage('user', query),), tools=tools.schemas())
    messages, schemas = capture.captured
    from emporio.llm_local import _serialize_message
    payload = {'model': capture.model, 'stream': True,
               'messages': [_serialize_message(m) for m in messages]}
    if schemas:
        payload['tools'] = list(schemas)
    report('direct_start', prompt_chars=sum(len(m.content) for m in messages),
           tools=[s['function']['name'] for s in schemas])
    started = monotonic()
    req = Request(capture.base_url + '/api/chat', data=json.dumps(payload).encode(),
                  headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=240) as response:
        report('headers', elapsed=round(monotonic()-started, 3))
        first = True
        for line in response:
            data = json.loads(line)
            if first:
                report('first_chunk', elapsed=round(monotonic()-started, 3))
                first = False
            if data.get('done'):
                report('direct_done', elapsed=round(monotonic()-started, 3),
                       metrics={k:v for k,v in data.items() if k.endswith('_duration') or k.endswith('_count')})

    run_runtime(root, query)


def run_runtime(root, query):
    llm, tools, _ = runtime_llm_and_tools(LocalLlamaLLM(model='llama3.1:latest', timeout=os.getenv('EMPORIO_LLAMA_TIMEOUT', '180')))
    sessions = SessionService(SQLiteSessionRepository.connect(root / 'data/diagnostic-session.db'))
    session_id = None
    if '--with-history' in sys.argv:
        context = sessions.create_session()
        session_id = str(context.session_id)
        for _ in range(6):
            sessions.append_message(session_id, 'user', 'Pergunta anterior sem relacao com o produto atual')
            sessions.append_message(session_id, 'assistant', 'Resposta anterior extensa. ' * 40)
    app = ConversationService(sessions, llm, tools)
    started = monotonic()
    import threading
    from uuid import uuid4
    from http.client import HTTPConnection
    from emporio.dev_console import DevConsoleApplication, create_server
    console = DevConsoleApplication(app, str(root / 'data/diagnostic-events.db'))
    server = create_server(console, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if '--followup-payment' in sys.argv:
            first = HTTPConnection('127.0.0.1', server.server_address[1], timeout=420)
            first.request('POST', '/api/messages', json.dumps({
                'message_id': str(uuid4()), 'text': 'Quanto custa o Shelby SN-100 Folk Aço Preto?',
            }), {'Content-Type': 'application/json'})
            first_response = first.getresponse()
            first_result = json.loads(first_response.read())
            first.close()
            report('first_turn', outcome=first_result.get('outcome'),
                   catalog=first_result.get('catalog'), answer=first_result.get('response'))
            assert first_result.get('catalog', {}).get('total') == 1, 'First turn did not uniquely resolve the product'
            session_id = first_result['session_id']
            query = 'Quais as condições de pagamento desse produto?'
        connection = HTTPConnection('127.0.0.1', server.server_address[1], timeout=420)
        connection.request('POST', '/api/messages', json.dumps({
            'message_id': str(uuid4()), 'text': query, 'session_id': session_id,
        }), {'Content-Type': 'application/json'})
        response = connection.getresponse()
        result = json.loads(response.read())
        connection.close()
        trace = result.pop('trace', None)
        if trace:
            report('trace_steps', trace_id=trace['trace_id'], steps=[
                {'stage': e['stage'], 'status': e['status'], 'data': e['data']}
                for e in trace['events'] if e['stage'] in ('routing', 'llm_started', 'tool_started')])
        report('http_runtime_done', elapsed=round(monotonic()-started, 3),
               status=response.status, result=result)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
