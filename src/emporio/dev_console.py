"""Local-only development console for exercising the real conversation pipeline."""
# ruff: noqa: E501

from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from .config import database_path
from .conversation import ConversationService
from .llm import LLMFactory
from .policy_runtime import runtime_llm_and_tools
from .session_service import SessionService
from .session_sqlite import SQLiteSessionRepository
from .store_hours import configured_hours_notice
from .simulators import MockWhatsAppChannel, mock_whatsapp_config
from .whatsapp import WhatsAppWebhookAdapter, WhatsAppVerificationError
from .tracing import TraceStore, action_trace
from .order import AuthorizedPrincipal
from .order_simulation import SimulationError, SimulationAccessError

MAX_BODY_BYTES = 64 * 1024
MAX_TEXT_CHARS = 4000
MAX_FIELD_CHARS = 200
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080


HTML = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Empório — Console de teste</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, system-ui, sans-serif; }
    body { margin: 0; background: #111827; color: #e5e7eb; }
    main { max-width: 900px; margin: 0 auto; padding: 32px 20px; }
    h1 { margin: 0 0 8px; font-size: 28px; }
    .muted { color: #9ca3af; }
    .panel { background: #1f2937; border: 1px solid #374151; border-radius: 14px; padding: 18px; margin-top: 18px; }
    label { display: block; margin: 12px 0 6px; color: #d1d5db; }
    input, textarea, select, button { box-sizing: border-box; width: 100%; border-radius: 8px; border: 1px solid #4b5563; padding: 10px; font: inherit; }
    input, textarea, select { background: #111827; color: #f9fafb; }
    textarea { min-height: 110px; resize: vertical; }
    button { margin-top: 14px; background: #f59e0b; color: #111827; border: 0; font-weight: 700; cursor: pointer; }
    button:hover { background: #fbbf24; }
    pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #030712; border-radius: 8px; padding: 14px; min-height: 80px; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    #answer { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.6; }
    .table-scroll { overflow-x: auto; margin-top: 16px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 12px; border-bottom: 1px solid #4b5563; text-align: left; }
    th { color: #fbbf24; }
    td:nth-child(2), td:nth-child(3) { white-space: nowrap; }
    summary { cursor: pointer; margin-top: 20px; color: #9ca3af; }
    button:disabled { opacity: .6; cursor: wait; }
    @media (max-width: 650px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
<main>
  <h1>Console de teste do Empório</h1>
  <p class="muted">Fluxo local: WhatsApp simulado → ConversationService → LLM → SQLite.</p>
  <section class="panel">
    <div class="grid">
      <div><label for="sender">Remetente</label><input id="sender" value="5511999999999"></div>
      <div><label for="messageId">ID da mensagem</label><input id="messageId"></div>
    </div>
    <label for="sessionId">Sessão (preenchida automaticamente)</label>
    <input id="sessionId" placeholder="nova sessão">
    <label for="text">Mensagem</label>
    <textarea id="text" placeholder="Ex.: Qual é o prazo de entrega para São Paulo?"></textarea>
    <button id="send">Enviar mensagem simulada</button>
  </section>
  <section class="panel" id="simulationPanel" hidden>
    <h2>Pedido de teste</h2>
    <p class="muted">Simulação local: sem cobrança, reserva de estoque ou envio real. Total dos produtos sem frete. Os pedidos ficam salvos em uma base de teste separada.</p>
    <button id="startSimulation">Iniciar novo cliente de teste</button>
    <p id="simulationStatus" role="status" aria-live="polite">Inicie um cliente para criar pedidos.</p>
    <div class="grid">
      <div><label for="simProduct">ID do produto (coluna ID do catálogo)</label><input type="number" id="simProduct" min="1" placeholder="Ex.: 89"></div>
      <div><label for="simQuantity">Quantidade</label><input type="number" id="simQuantity" min="1" max="99" value="1"></div>
    </div>
    <label for="simPayment">Pagamento simulado</label>
    <select id="simPayment"><option value="pix">PIX</option><option value="credit_card">Cartão à vista</option><option value="debit">Débito</option><option value="boleto">Boleto</option></select>
    <button id="createSimOrder" disabled>Criar pedido fictício</button>
    <p class="muted">Últimos 30 pedidos deste cliente de teste.</p>
    <div id="simOrders"></div>
  </section>
  <section class="panel">
    <h2>Resposta</h2>
    <div id="answer" role="status" aria-live="polite">Aguardando mensagem...</div>
    <section id="catalog" hidden aria-label="Produtos encontrados">
      <div class="table-scroll">
        <table>
          <caption id="catalogCaption"></caption>
          <thead><tr><th scope="col">Modelo</th><th scope="col">Preço</th><th scope="col">Estoque</th><th scope="col">ID</th></tr></thead>
          <tbody id="products"></tbody>
        </table>
      </div>
      <p id="catalogNote" class="muted"></p>
    </section>
    <details><summary>Diagnóstico (JSON)</summary><pre id="response"></pre></details>
    <details open><summary>Rastreamento desta mensagem</summary>
      <p id="traceStatus" class="muted">Nenhuma consulta registrada.</p>
      <ol id="timeline"></ol>
      <details><summary>Dados do rastreamento</summary><pre id="traceData"></pre></details>
    </details>
    <details><summary>Histórico e métricas</summary>
      <button id="loadHistory">Atualizar histórico</button>
      <p id="metrics" class="muted"></p><div id="historyList"></div>
    </details>
  </section>
</main>
<script>
const id = (name) => document.getElementById(name);
id('messageId').value = 'dev-' + crypto.randomUUID();
function renderCatalog(catalog) {
  id('products').replaceChildren();
  id('catalog').hidden = !catalog;
  if (!catalog) return;
  const products = Array.isArray(catalog.products) ? catalog.products : [];
  const brl = new Intl.NumberFormat('pt-BR', {style: 'currency', currency: 'BRL'});
  for (const product of products) {
    const row = document.createElement('tr');
    const values = [product.name, brl.format(Number(product.price_brl)), product.stock_quantity, product.product_id || '—'];
    for (const value of values) {
      const cell = document.createElement('td');
      cell.textContent = String(value);
      row.appendChild(cell);
    }
    id('products').appendChild(row);
  }
  id('catalogCaption').textContent = products.length
    ? `${products.length} de ${catalog.total} produtos encontrados`
    : 'Nenhum produto encontrado para estes filtros.';
  const date = catalog.snapshot && catalog.snapshot.data_as_of;
  id('catalogNote').textContent = date
    ? `Dados do snapshot de ${date}. Estoque e valores sujeitos a atualizacao.`
    : 'Disponibilidade baseada no snapshot do catalogo.';
}
const stages = {
  message_received: 'Mensagem recebida', session_ready: 'Sessao e persistencia',
  routing: 'Escolha da fonte e ferramentas', rag: 'Busca nas politicas (RAG)',
  llm_started: 'Llama iniciada — aguardando resposta', llm_completed: 'Llama respondeu',
  llm_error: 'Falha na Llama', tool_started: 'Ferramenta iniciada',
  tool_completed: 'Ferramenta concluida', catalog_result: 'Resultado do catalogo',
  policy_guard: 'Validacao da politica', response_ready: 'Resposta preparada',
  persistence: 'Persistencia da conversa',
  payment_plan: 'Consulta obrigatoria para pagamento',
  tracking_plan: 'Consulta do pedido de teste', simulation_action: 'Ação explícita de simulação',
  simulation_order: 'Mudança no pedido fictício', tracking_result: 'Rastreio verificado na simulação',
  response_fallback: 'Resposta preservada com informacoes verificadas',
  response_validation: 'Validacao da resposta gerada',
  product_reference_resolved: 'Produto identificado no contexto da sessao',
  clarification_required: 'Selecao de produto necessaria',
  request_error: 'Falha no processamento', conversation_event: 'Etapa da conversa'
};
function renderTrace(trace, waitingMs) {
  id('timeline').replaceChildren();
  id('traceData').textContent = trace ? JSON.stringify(trace, null, 2) : '';
  if (!trace) { id('traceStatus').textContent = 'Aguardando inicio do rastreamento...'; return; }
  const elapsed = waitingMs == null ? (trace.duration_ms || 0) : waitingMs;
  id('traceStatus').textContent = `ID: ${trace.trace_id} | ${(elapsed / 1000).toFixed(1)} s | ${trace.outcome || (waitingMs == null ? 'concluido' : 'processando')}`;
  for (const item of trace.events || []) {
    const line = document.createElement('li');
    const details = item.data || {};
    let suffix = details.tool ? ` | ${details.tool}` : '';
    if (details.product_id != null) suffix += ` | produto #${details.product_id}`;
    if (details.passages != null) suffix += ` | ${details.passages} trechos`;
    if (details.total != null) suffix += ` | ${details.total} produtos`;
    if (details.error_class) suffix += ` | ${details.error_class}`;
    if (details.prompt_tokens != null) suffix += ` | prompt: ${details.prompt_tokens} tokens / ${Math.round(details.prompt_ms || 0)} ms | geracao: ${details.generated_tokens || 0} tokens / ${Math.round(details.generation_ms || 0)} ms | carga: ${Math.round(details.load_ms || 0)} ms`;
    if (details.sources) suffix += ' | ' + details.sources.map(s => `${s.file}, pagina ${s.page}, score ${s.score}`).join('; ');
    line.textContent = `${(item.offset_ms / 1000).toFixed(1)} s — ${stages[item.stage] || item.stage}: ${item.status} (${item.duration_ms} ms)${suffix}`;
    id('timeline').appendChild(line);
  }
}
id('loadHistory').addEventListener('click', async () => {
  try {
    const [historyResponse, metricsResponse] = await Promise.all([fetch('/api/traces'), fetch('/api/metrics')]);
    if (!historyResponse.ok || !metricsResponse.ok) throw new Error('Historico indisponivel');
    const history = await historyResponse.json();
    const metrics = await metricsResponse.json();
    id('metrics').textContent = `${metrics.sample_size} consultas concluidas | mediana ${(metrics.latency_ms.p50 / 1000).toFixed(1)} s | p95 ${(metrics.latency_ms.p95 / 1000).toFixed(1)} s | ${JSON.stringify(metrics.outcomes)}`;
    id('historyList').replaceChildren();
    for (const trace of history.traces) {
      const button = document.createElement('button');
      button.textContent = `${new Date(trace.started * 1000).toLocaleString('pt-BR')} | ${trace.outcome} | ${trace.trace_id}`;
      button.addEventListener('click', async () => {
        const result = await fetch('/api/traces/' + encodeURIComponent(trace.trace_id));
        if (result.ok) renderTrace(await result.json());
      });
      id('historyList').appendChild(button);
    }
  } catch (error) { id('metrics').textContent = String(error); }
});
id('send').addEventListener('click', async () => {
  const requestToken = simulationToken;
  const payload = {
    sender: id('sender').value,
    message_id: id('messageId').value,
    session_id: id('sessionId').value || null,
    text: id('text').value
  };
  id('send').disabled = true;
  id('answer').textContent = 'Processando...';
  id('response').textContent = '';
  renderCatalog(null);
  renderTrace(null);
  const startedAt = Date.now();
  let polling = true;
  let pollTimer;
  const poll = async () => {
    try {
      const result = await fetch('/api/traces/by-message/' + encodeURIComponent(payload.message_id));
      if (result.ok) {
        const trace = await result.json();
        if (polling && requestToken === simulationToken) renderTrace(trace, Date.now() - startedAt);
      }
    } catch (_) { /* Message processing continues if history is temporarily unavailable. */ }
    if (polling) pollTimer = setTimeout(poll, 1500);
  };
  poll();
  try {
    const result = await fetch('/api/messages', {
      method: 'POST', headers: simulationHeaders(), body: JSON.stringify(payload)
    });
    const data = await result.json();
    if (requestToken !== simulationToken || id('sessionId').value !== (payload.session_id || '')) return;
    if (data.session_id) id('sessionId').value = data.session_id;
    id('answer').textContent = data.response || data.error || (data.duplicate ? 'Mensagem ja processada.' : 'Sem resposta.');
    if (data.catalog && data.outcome === 'provider_failure') {
      id('answer').textContent = 'O catalogo foi consultado. Confira os resultados na tabela abaixo. A resposta em texto do assistente nao pode ser concluida nesta tentativa.';
    }
    renderCatalog(data.catalog);
    id('response').textContent = JSON.stringify(data, null, 2);
    polling = false;
    renderTrace(data.trace);
    if (data.accepted) id('messageId').value = 'dev-' + crypto.randomUUID();
  } catch (error) { id('answer').textContent = 'Falha de conexao: ' + error; }
  finally { polling = false; clearTimeout(pollTimer); id('send').disabled = false; }
});
let simulationToken = '';
try { simulationToken = sessionStorage.getItem('emporioSimulationToken') || ''; } catch (_) {}
function simulationHeaders() {
  return {'Content-Type': 'application/json', ...(simulationToken ? {'X-Emporio-Simulation-Token': simulationToken} : {})};
}
async function simulationRequest(path, payload) {
  const result = await fetch(path, {method: payload === undefined ? 'GET' : 'POST', headers: simulationHeaders(),
    ...(payload === undefined ? {} : {body: JSON.stringify(payload)})});
  const data = await result.json();
  if (!result.ok) throw new Error(data.error || 'Falha na simulação');
  return data;
}
function renderSimOrders(orders) {
  id('simOrders').replaceChildren();
  const labels = {awaiting_payment: 'Aguardando pagamento', paid: 'Pagamento simulado aprovado', shipped: 'Despachado na simulação'};
  for (const order of orders || []) {
    const section = document.createElement('section');
    const details = document.createElement('p');
    details.textContent = `${order.order_reference} — ${order.product_name} × ${order.quantity} | R$ ${order.total_brl} sem frete | ${labels[order.status] || order.status}`;
    section.appendChild(details);
    if (order.tracking) {
      const tracking = document.createElement('p');
      tracking.textContent = `Rastreio fictício: ${order.tracking.code} | ${order.tracking.status} (${order.tracking.source})`;
      section.appendChild(tracking);
    }
    if (order.notification) {
      const notice = document.createElement('p');
      notice.textContent = `${order.notification.channel}: ${order.notification.message}`;
      section.appendChild(notice);
    }
    const audit = document.createElement('details');
    const summary = document.createElement('summary'); summary.textContent = 'Histórico do pedido fictício';
    const data = document.createElement('pre'); data.textContent = JSON.stringify(order.events, null, 2);
    audit.appendChild(summary); audit.appendChild(data); section.appendChild(audit);
    if (order.status !== 'shipped') {
      const action = order.status === 'awaiting_payment' ? 'pay' : 'ship';
      const button = document.createElement('button');
      button.textContent = action === 'pay' ? 'Simular aprovação do pagamento' : 'Simular despacho e gerar rastreio';
      button.addEventListener('click', async () => {
        button.disabled = true;
        try {
          const result = await simulationRequest(`/api/simulation/orders/${encodeURIComponent(order.order_reference)}/${action}`, {});
          id('simulationStatus').textContent = `Ação simulada registrada. ID de rastreamento: ${result.trace_id}`;
          await refreshSimulation();
        } catch (error) { id('simulationStatus').textContent = String(error); button.disabled = false; }
      });
      section.appendChild(button);
    }
    const consult = document.createElement('button');
    consult.textContent = 'Preparar consulta de rastreio na conversa';
    consult.addEventListener('click', () => {
      id('text').value = `Qual o rastreio do pedido ${order.order_reference}?`;
      id('simulationStatus').textContent = 'Pergunta preparada. Clique em Enviar mensagem simulada para consultar pelo assistente.';
    });
    section.appendChild(consult);
    for (const request of order.post_sale || []) {
      const line = document.createElement('p');
      line.textContent = `${request.kind === 'complaint' ? 'Reclamação' : 'Devolução'} simulada #${request.id}: ${request.description} — aguardando análise`;
      section.appendChild(line);
      if (request.kind === 'return') {
        const code = document.createElement('p');
        code.textContent = `Código fictício: ${request.return_code} — elegibilidade pendente`;
        section.appendChild(code);
        const instructions = document.createElement('ol');
        for (const instruction of request.instructions) {
          const item = document.createElement('li'); item.textContent = instruction;
          instructions.appendChild(item);
        }
        section.appendChild(instructions);
      }
    }
    for (const [kind, label] of [['complaint', 'Registrar reclamação simulada'], ['return', 'Solicitar devolução simulada']]) {
      const input = document.createElement('input');
      input.placeholder = kind === 'complaint' ? 'Descreva a reclamação' : 'Descreva o motivo da devolução';
      input.maxLength = 500;
      const button = document.createElement('button');
      button.textContent = label;
      let pending = null;
      button.addEventListener('click', async () => {
        const description = input.value.trim();
        if (!description) { id('simulationStatus').textContent = 'Informe uma descrição.'; return; }
        if (!pending || pending.description !== description) pending = {description, request_id: crypto.randomUUID()};
        button.disabled = true;
        try {
          await simulationRequest(`/api/simulation/orders/${encodeURIComponent(order.order_reference)}/${kind}`, pending);
          id('simulationStatus').textContent = 'Solicitação simulada registrada e aguardando análise.';
          await refreshSimulation();
        } catch (error) { id('simulationStatus').textContent = String(error); button.disabled = false; }
      });
      section.appendChild(input); section.appendChild(button);
    }
    id('simOrders').appendChild(section);
  }
}
async function refreshSimulation() {
  const data = await simulationRequest('/api/simulation');
  id('simulationPanel').hidden = !data.enabled;
  if (data.session_id) {
    id('sessionId').value = data.session_id;
    id('sessionId').readOnly = true;
    id('createSimOrder').disabled = false;
    renderSimOrders(data.orders);
  }
}
id('startSimulation').addEventListener('click', async () => {
  id('startSimulation').disabled = true;
  try {
    const data = await simulationRequest('/api/simulation/start', {});
    simulationToken = data.token;
    try { sessionStorage.setItem('emporioSimulationToken', simulationToken); } catch (_) {}
    id('sessionId').value = data.session_id;
    id('messageId').value = 'dev-' + crypto.randomUUID();
    id('simulationStatus').textContent = `${data.label} ativo. Sessão vinculada automaticamente.`;
    await refreshSimulation();
  } catch (error) { id('simulationStatus').textContent = String(error); }
  finally { id('startSimulation').disabled = false; }
});
let pendingSimOrder = null;
id('createSimOrder').addEventListener('click', async () => {
  id('createSimOrder').disabled = true;
  const fields = {product_id: Number(id('simProduct').value), quantity: Number(id('simQuantity').value), payment_method: id('simPayment').value};
  const signature = JSON.stringify(fields);
  if (!pendingSimOrder || pendingSimOrder.signature !== signature) pendingSimOrder = {signature, request_id: crypto.randomUUID()};
  try {
    const data = await simulationRequest('/api/simulation/orders', {...fields, request_id: pendingSimOrder.request_id});
    pendingSimOrder = null;
    id('simulationStatus').textContent = `Pedido fictício ${data.order.order_reference} criado. Total sem frete.`;
    await refreshSimulation();
  } catch (error) { id('simulationStatus').textContent = String(error); }
  finally { id('createSimOrder').disabled = false; }
});
if (typeof window !== 'undefined') refreshSimulation().catch(error => {
  id('simulationPanel').hidden = false;
  id('simulationStatus').textContent = String(error) + '. Inicie um novo cliente se a sessão expirou.';
});
</script>
</body>
</html>"""


def _flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "on"}


def _bounded_text(value: Any, field: str, maximum: int = MAX_FIELD_CHARS) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field} is required and bounded")
    return value.strip()


class _SessionConversation:
    def __init__(self, service: ConversationService, session_id: str | None, message_id: str, principal=None) -> None:
        self.service, self.session_id = service, session_id or None
        self.message_id = message_id
        self.principal = principal

    def respond(self, text: str) -> Any:
        kwargs = {'principal': self.principal} if self.principal is not None else {}
        return self.service.respond(text, session_id=self.session_id, message_id=self.message_id, **kwargs)


class DevConsoleApplication:
    def __init__(self, conversation: ConversationService, idempotency_db: str | None = None) -> None:
        self.conversation = conversation
        self.simulator = getattr(getattr(conversation, 'tools', None), 'order_simulator', None)
        self.policy_grounded = getattr(conversation.llm, "policy", None) is not None
        self.policy_source = os.getenv("EMPORIO_POLICY_SOURCE", "")
        self.database = str(database_path())
        path = idempotency_db or os.getenv("EMPORIO_DEV_IDEMPOTENCY_DB")
        if not path:
            path = str(database_path().with_name("dev-whatsapp-events.db"))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.channel = MockWhatsAppChannel(
            WhatsAppWebhookAdapter(mock_whatsapp_config(idempotency_db_path=path))
        )

    def simulation(self, path, payload=None, token=None):
        if self.simulator is None:
            if path == '/api/simulation' and payload is None:
                return HTTPStatus.OK, {'enabled': False}
            return HTTPStatus.NOT_FOUND, {'error': 'Simulação de pedidos desativada.'}
        if path == '/api/simulation' and payload is None:
            if not token:
                return HTTPStatus.OK, {'enabled': True}
            client = self.simulator.client(token)
            return HTTPStatus.OK, {'enabled': True, 'session_id': client['session_id'],
                                   'orders': self.simulator.list_orders(client)}
        if not isinstance(payload, dict):
            raise SimulationError('Informe um objeto JSON.')
        if path == '/api/simulation/start':
            with action_trace() as trace:
                result = self.simulator.start_client(self.conversation.sessions)
            return HTTPStatus.OK, {**result, 'trace_id': trace.trace_id}
        client = self.simulator.client(token)
        with action_trace(client['session_id']) as trace:
            if path == '/api/simulation/orders':
                order = self.simulator.create_order(client, payload)
            else:
                parts = path.split('/')
                if len(parts) != 6 or parts[:4] != ['', 'api', 'simulation', 'orders'] or parts[5] not in {'pay', 'ship', 'complaint', 'return'}:
                    return HTTPStatus.NOT_FOUND, {'error': 'Ação de simulação inexistente.'}
                if parts[5] in {'complaint', 'return'}:
                    requests = self.simulator.post_sale(AuthorizedPrincipal(client['customer_id']), parts[4],
                                                        parts[5], payload.get('description'), payload.get('request_id'))
                    return HTTPStatus.OK, {'post_sale': requests, 'trace_id': trace.trace_id}
                order = self.simulator.transition(client, parts[4], parts[5])
        return HTTPStatus.OK, {'order': order, 'trace_id': trace.trace_id}

    def message(self, payload: Any, simulation_token=None) -> tuple[int, dict[str, Any]]:
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        text = _bounded_text(payload.get("text"), "text", MAX_TEXT_CHARS)
        message_id = _bounded_text(payload.get("message_id"), "message_id")
        sender = _bounded_text(payload.get("sender", "5511999999999"), "sender")
        session_id = payload.get("session_id")
        if session_id is not None:
            session_id = _bounded_text(session_id, "session_id")
        principal = None
        if simulation_token:
            if self.simulator is None:
                raise SimulationAccessError('Simulação de pedidos desativada.')
            client = self.simulator.client(simulation_token)
            if session_id != client['session_id']:
                raise SimulationAccessError('Use a sessão vinculada ao cliente de teste.')
            principal = AuthorizedPrincipal(client['customer_id'])
        result = self.channel.deliver(
            _SessionConversation(self.conversation, session_id, message_id, principal),
            message_id=message_id,
            sender=sender,
            text=text,
        )
        outcome = result.response
        diagnostics = getattr(outcome, 'diagnostics', {})
        trace = getattr(outcome, 'trace', None)
        if trace is None and result.duplicate:
            try:
                trace = TraceStore().by_message(message_id)
            except Exception:
                trace = None
        response_session = getattr(outcome, "session_id", session_id)
        if principal is not None and response_session is not None and str(response_session) != client['session_id']:
            self.simulator.bind_session(client, response_session)
        body = {
            "accepted": result.accepted,
            "duplicate": result.duplicate,
            "message_id": result.message.message_id if result.message else message_id,
            "session_id": str(response_session) if response_session is not None else None,
            "response": getattr(outcome, "text", None),
            "catalog": getattr(outcome, "catalog", None),
            "trace": trace,
            "trace_id": trace['trace_id'] if trace else getattr(outcome, 'correlation_id', None),
            "outcome": getattr(outcome, "outcome", "duplicate" if result.duplicate else None),
            "provider": getattr(self.conversation.llm, "provider", "unknown"),
            "model": getattr(self.conversation.llm, "model", "unknown"),
            "tool_calls": getattr(outcome, "tool_calls", 0),
            "persistence": getattr(getattr(outcome, "persistence", None), "value", None),
            "policy_grounded": self.policy_grounded,
            "policy_source_configured": bool(self.policy_source),
            "policy_evidence_available": diagnostics.get('policy_evidence_available', False),
            "policy_evidence_preview": diagnostics.get('policy_evidence_preview'),
            "policy_query": text if self.policy_grounded else None,
            "policy_error": diagnostics.get('policy_error'),
            "provider_error": diagnostics.get('provider_error'),
            "provider_timeout": getattr(getattr(self.conversation.llm, "delegate", self.conversation.llm), "timeout", None),
            "registered_tools": list(self.conversation.tools.names()),
            "runtime_log_path": os.getenv("EMPORIO_RUNTIME_LOG", "data/emporio-runtime.log"),
            "database_path": self.database,
        }
        return HTTPStatus.OK, body


def create_default_application() -> DevConsoleApplication:
    repository = SQLiteSessionRepository.connect(database_path())
    llm, tools, _policy = runtime_llm_and_tools(LLMFactory.create())
    return DevConsoleApplication(
        ConversationService(
            SessionService(repository), llm, tools, hours_notice=configured_hours_notice()
        )
    )


def create_server(application: DevConsoleApplication, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
    if host not in {"127.0.0.1", "localhost"} and not (host == "0.0.0.0" and _flag("EMPORIO_DEV_CONSOLE_ALLOW_CONTAINER_BIND")):
        raise ValueError("development console must bind to localhost")

    class Handler(BaseHTTPRequestHandler):
        server_version = "EmporioDevConsole/1.0"

        def _write(self, status: int, body: Any, content_type: str = "application/json") -> None:
            raw = body.encode("utf-8") if isinstance(body, str) else json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == '/api/simulation':
                try:
                    status, body = application.simulation(self.path, token=self.headers.get('X-Emporio-Simulation-Token'))
                except SimulationError as exc:
                    status, body = exc.status, {'error': str(exc)}
                except Exception:
                    status, body = HTTPStatus.SERVICE_UNAVAILABLE, {'error': 'Simulação indisponível.'}
                self._write(status, body)
            elif self.path == "/":
                self._write(HTTPStatus.OK, HTML, "text/html")
            elif self.path == "/health":
                self._write(HTTPStatus.OK, {"status": "ok", "mode": "development"})
            elif self.path.startswith('/api/traces') or self.path == '/api/metrics':
                try:
                    store = TraceStore()
                    if self.path == '/api/traces':
                        body = {'traces': store.recent()}
                    elif self.path == '/api/metrics':
                        body = store.metrics()
                    elif self.path.startswith('/api/traces/by-message/'):
                        identity = unquote(self.path.removeprefix('/api/traces/by-message/'))
                        if len(identity) > MAX_FIELD_CHARS:
                            raise ValueError('invalid message identifier')
                        body = store.by_message(identity)
                    else:
                        body = store.get(self.path.removeprefix('/api/traces/'))
                    self._write(HTTPStatus.OK if body is not None else HTTPStatus.NOT_FOUND,
                                body if body is not None else {'error': 'trace not found'})
                except ValueError:
                    self._write(HTTPStatus.BAD_REQUEST, {'error': 'invalid trace identifier'})
                except Exception:
                    self._write(HTTPStatus.SERVICE_UNAVAILABLE, {'error': 'trace history unavailable'})
            else:
                self._write(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/messages" and not self.path.startswith('/api/simulation/'):
                self._write(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            length = self.headers.get("Content-Length", "")
            try:
                size = int(length)
            except ValueError:
                size = 0
            if not 1 <= size <= MAX_BODY_BYTES:
                self._write(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request body is invalid"})
                return
            try:
                payload = json.loads(self.rfile.read(size).decode("utf-8"))
                token = self.headers.get('X-Emporio-Simulation-Token')
                if self.path.startswith('/api/simulation/'):
                    status, body = application.simulation(self.path, payload, token)
                else:
                    status, body = application.message(payload, token) if token else application.message(payload)
            except SimulationError as exc:
                status, body = exc.status, {'error': str(exc)}
            except (UnicodeError, json.JSONDecodeError, ValueError, WhatsAppVerificationError):
                status, body = HTTPStatus.BAD_REQUEST, {"error": "invalid development message"}
            except Exception:  # noqa: BLE001 - never leak a development traceback
                status, body = HTTPStatus.SERVICE_UNAVAILABLE, {"error": "conversation unavailable"}
            self._write(status, body)

        def _method_not_allowed(self) -> None:
            self._write(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method not allowed"})

        do_PUT = _method_not_allowed
        do_PATCH = _method_not_allowed
        do_DELETE = _method_not_allowed

        def log_message(self, *_args: Any) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def serve(application: DevConsoleApplication | None = None) -> ThreadingHTTPServer:
    if not _flag("EMPORIO_DEV_CONSOLE_ENABLED"):
        raise RuntimeError("set EMPORIO_DEV_CONSOLE_ENABLED=true to enable the dev console")
    raw_port = os.getenv("EMPORIO_DEV_CONSOLE_PORT")
    if not raw_port:
        raise RuntimeError("set EMPORIO_DEV_CONSOLE_PORT to enable the dev console")
    try:
        port = int(raw_port)
    except ValueError:
        raise ValueError("EMPORIO_DEV_CONSOLE_PORT must be an integer") from None
    if not 1 <= port <= 65535:
        raise ValueError("EMPORIO_DEV_CONSOLE_PORT must be between 1 and 65535")
    host = "0.0.0.0" if _flag("EMPORIO_DEV_CONSOLE_ALLOW_CONTAINER_BIND") else DEFAULT_HOST
    server = create_server(application or create_default_application(), host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return server
