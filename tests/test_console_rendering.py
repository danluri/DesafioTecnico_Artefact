"""Exercise the embedded console renderer with a minimal DOM in Node."""

import shutil
import subprocess

import pytest

from emporio.dev_console import HTML


@pytest.mark.skipif(not shutil.which('node'), reason='Node required for console JavaScript check')
def test_catalog_table_formats_data_safely_and_clears_old_results():
    script = HTML.split('<script>', 1)[1].split('</script>', 1)[0]
    harness = r"""
const assert = require('node:assert/strict');
class Element {
  constructor() { this.children = []; this.textContent = ''; this.hidden = false; this.listeners = {}; this.value = ''; }
  replaceChildren() { this.children = []; }
  appendChild(child) { this.children.push(child); }
  addEventListener(type, listener) { this.listeners[type] = listener; }
}
const elements = new Map();
global.document = {
  getElementById(name) {
    if (!elements.has(name)) elements.set(name, new Element());
    return elements.get(name);
  },
  createElement() { return new Element(); }
};
global.crypto = {randomUUID: () => 'test-id'};
const storage = new Map();
global.sessionStorage = {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value)};
"""
    checks = r"""
renderCatalog({products: [{name: '<img src=x onerror=alert(1)>', price_brl: '599.90', stock_quantity: 7}],
  total: 12, snapshot: {data_as_of: '2026-11-04'}});
assert.equal(id('catalog').hidden, false);
const cells = id('products').children[0].children;
assert.equal(cells[0].textContent, '<img src=x onerror=alert(1)>');
assert.equal(cells[0].children.length, 0);
assert.match(cells[1].textContent, /R\$\s599,90/);
assert.equal(cells[2].textContent, '7');
assert.match(id('catalogCaption').textContent, /1 de 12/);
assert.match(id('catalogNote').textContent, /2026-11-04/);
renderCatalog({products: [], total: 0});
assert.equal(id('products').children.length, 0);
assert.match(id('catalogCaption').textContent, /Nenhum produto/);
renderCatalog(null);
assert.equal(id('catalog').hidden, true);
assert.equal(id('products').children.length, 0);
renderTrace({trace_id: 'trace-123', duration_ms: 1200, outcome: 'success', events: [
  {stage: 'rag', status: 'success', offset_ms: 10, duration_ms: 5,
   data: {passages: 1, sources: [{file: '<img src=x>', page: 2, score: 3}]}},
  {stage: 'llm_completed', status: 'success', offset_ms: 1200, duration_ms: 1100,
   data: {prompt_tokens: 20, generated_tokens: 3, prompt_ms: 10, generation_ms: 1000}}
]});
assert.match(id('traceStatus').textContent, /trace-123/);
assert.equal(id('timeline').children.length, 2);
assert.match(id('timeline').children[0].textContent, /pagina 2/);
assert.equal(id('timeline').children[0].children.length, 0);
assert.match(id('timeline').children[1].textContent, /20 tokens/);
assert.match(id('traceData').textContent, /trace-123/);
renderTrace(null);
assert.equal(id('timeline').children.length, 0);
renderSimOrders([{order_reference: 'SIM-000001', product_name: '<img src=x>', quantity: 1,
  total_brl: '521.55', status: 'awaiting_payment', events: []}]);
assert.equal(id('simOrders').children.length, 1);
const order = id('simOrders').children[0];
assert.match(order.children[0].textContent, /<img src=x>/);
assert.equal(order.children[0].children.length, 0);
assert.match(order.children[2].textContent, /aprovação do pagamento/);
renderSimOrders([{order_reference: 'SIM-000001', product_name: 'Shelby', quantity: 1,
  total_brl: '521.55', status: 'shipped', events: [],
  tracking: {code: 'BR123456789BR', status: 'Em trânsito', source: 'Mock Correios'},
  notification: {channel: 'WhatsApp simulado', message: 'Teste'}}]);
assert.match(id('simOrders').children[0].children[1].textContent, /BR123456789BR/);
assert.match(id('simOrders').children[0].children[2].textContent, /WhatsApp simulado/);
renderSimOrders([]);
assert.equal(id('simOrders').children.length, 0);
(async () => {
  const requests = [];
  global.fetch = async (path, options = {}) => {
    requests.push({path, options});
    let data;
    if (path === '/api/simulation/start') data = {token: 'server-issued-token', session_id: 'server-session', label: 'Cliente fictício 1'};
    else if (path === '/api/simulation') data = {enabled: true, session_id: 'server-session', orders: []};
    else if (path === '/api/simulation/orders') data = {order: {order_reference: 'SIM-000001'}};
    else if (path === '/api/messages') data = {accepted: true, response: 'Resposta autenticada', session_id: 'server-session'};
    else return {ok: false};
    return {ok: true, json: async () => data};
  };
  await id('startSimulation').listeners.click();
  assert.equal(storage.get('emporioSimulationToken'), 'server-issued-token');
  assert.equal(id('sessionId').value, 'server-session');
  assert.equal(id('sessionId').readOnly, true);
  id('simProduct').value = '89'; id('simQuantity').value = '1'; id('simPayment').value = 'pix';
  await id('createSimOrder').listeners.click();
  const creation = requests.find(r => r.path === '/api/simulation/orders');
  assert.equal(creation.options.headers['X-Emporio-Simulation-Token'], 'server-issued-token');
  assert.equal(JSON.parse(creation.options.body).product_id, 89);
  id('text').value = 'Qual o rastreio do pedido SIM-000001?';
  await id('send').listeners.click();
  const message = requests.find(r => r.path === '/api/messages');
  assert.equal(message.options.headers['X-Emporio-Simulation-Token'], 'server-issued-token');
  assert.equal(JSON.parse(message.options.body).session_id, 'server-session');
  assert.equal(id('answer').textContent, 'Resposta autenticada');
  let finishOldMessage;
  global.fetch = async path => {
    if (path !== '/api/messages') return {ok: false};
    return new Promise(resolve => { finishOldMessage = resolve; });
  };
  const pending = id('send').listeners.click();
  simulationToken = 'new-client-token';
  id('sessionId').value = 'new-client-session';
  finishOldMessage({ok: true, json: async () => ({session_id: 'old-session', response: 'Resposta antiga'})});
  await pending;
  assert.equal(id('sessionId').value, 'new-client-session');
  assert.notEqual(id('answer').textContent, 'Resposta antiga');
})().catch(error => { process.stderr.write(String(error)); process.exitCode = 1; });
"""
    result = subprocess.run([shutil.which('node')], input=harness + script + checks,
                            text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
