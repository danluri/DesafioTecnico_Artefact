"""Local-only order lifecycle. No real payment, stock reservation or carrier calls."""

from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import re
import secrets
import sqlite3

from .correios import generate_fake_tracking_code
from .order import AuthorizedPrincipal
from .payment_service import PaymentService
from .simulators import MockCorreiosTracking
from .tracing import trace_id, event, fingerprint


class SimulationError(ValueError):
    status = 400


class SimulationAccessError(SimulationError):
    status = 403


class SimulationConflict(SimulationError):
    status = 409


def now():
    return datetime.now(timezone.utc)


def post_sale_view(row):
    request = dict(row)
    if request['kind'] == 'return':
        request['return_code'] = f"DEV-SIM-{request['id']:08d}"
        request['eligibility'] = 'pending'
        request['instructions'] = [
            'Aguarde a análise de elegibilidade antes de enviar o produto.',
            'Se a devolução for aprovada, embale o produto com segurança e identifique a embalagem com o código fictício.',
            'Aguarde as orientações da loja para o envio; esta simulação não gera postagem real.',
        ]
    return request


class OrderSimulation:
    simulated = True

    def __init__(self, path, catalog):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.catalog = catalog
        with closing(self.connect()) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS sim_clients (
                    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_hash TEXT NOT NULL UNIQUE, session_id TEXT UNIQUE, expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sim_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER NOT NULL REFERENCES sim_clients(customer_id),
                    request_id TEXT NOT NULL, request_hash TEXT NOT NULL,
                    product_id INTEGER NOT NULL, product_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL, payment_method TEXT NOT NULL,
                    total_brl TEXT NOT NULL, snapshot_at TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('awaiting_payment','paid','shipped')),
                    created_at TEXT NOT NULL, paid_at TEXT, shipped_at TEXT, tracking_code TEXT,
                    UNIQUE(customer_id, request_id)
                );
                CREATE TABLE IF NOT EXISTS sim_order_events (
                    id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES sim_orders(id),
                    action TEXT NOT NULL, occurred_at TEXT NOT NULL, trace_id TEXT
                );
                CREATE TABLE IF NOT EXISTS sim_outbox (
                    order_id INTEGER PRIMARY KEY REFERENCES sim_orders(id),
                    channel TEXT NOT NULL, message TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sim_post_sale (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL REFERENCES sim_orders(id),
                    kind TEXT NOT NULL CHECK(kind IN ('complaint','return')),
                    description TEXT NOT NULL, request_id TEXT NOT NULL,
                    created_at TEXT NOT NULL, UNIQUE(order_id, request_id)
                );
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def start_client(self, sessions):
        token = secrets.token_urlsafe(32)
        with closing(self.connect()) as db, db:
            result = db.execute('INSERT INTO sim_clients(token_hash, expires_at) VALUES (?, ?)',
                                (fingerprint(token), (now()+timedelta(hours=24)).isoformat()))
            customer_id = result.lastrowid
            context = sessions.create_session(AuthorizedPrincipal(customer_id))
            if context.persistence.value != 'persisted':
                raise SimulationConflict('Não foi possível persistir a sessão de teste.')
            db.execute('UPDATE sim_clients SET session_id=? WHERE customer_id=?',
                       (str(context.session_id), customer_id))
        return {'simulated': True, 'token': token, 'session_id': str(context.session_id),
                'label': f'Cliente fictício {customer_id}'}

    def client(self, token):
        if not isinstance(token, str) or not 20 <= len(token) <= 200:
            raise SimulationAccessError('Cliente de teste não autorizado.')
        with closing(self.connect()) as db:
            row = db.execute('SELECT * FROM sim_clients WHERE token_hash=?', (fingerprint(token),)).fetchone()
        if row is None or datetime.fromisoformat(row['expires_at']) <= now():
            raise SimulationAccessError('Cliente de teste não autorizado ou expirado.')
        return dict(row)

    @staticmethod
    def reference(order_id):
        return f'SIM-{order_id:06d}'

    def bind_session(self, client, session_id):
        """Accept only a session returned by the trusted conversation service."""
        with closing(self.connect()) as db, db:
            db.execute('UPDATE sim_clients SET session_id=? WHERE customer_id=? AND token_hash=?',
                       (str(session_id), client['customer_id'], client['token_hash']))

    @staticmethod
    def parse(reference):
        if not isinstance(reference, str) or not re.fullmatch(r'SIM-\d{6,12}', reference.upper()):
            raise SimulationAccessError('Pedido de teste indisponível para este cliente.')
        return int(reference.split('-')[1])

    def create_order(self, client, payload):
        product_id, quantity = payload.get('product_id'), payload.get('quantity', 1)
        method, key = payload.get('payment_method', 'pix'), payload.get('request_id')
        if isinstance(product_id, bool) or not isinstance(product_id, int) or not 1 <= product_id <= 9223372036854775807:
            raise SimulationError('Informe um ID de produto válido.')
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 99:
            raise SimulationError('Quantidade deve estar entre 1 e 99.')
        if not isinstance(method, str) or method not in {'pix', 'credit_card', 'debit', 'boleto'}:
            raise SimulationError('Forma de pagamento de teste inválida.')
        if not isinstance(key, str) or not 1 <= len(key) <= 100:
            raise SimulationError('Identificador da criação é obrigatório.')
        signature = fingerprint(json.dumps([product_id, quantity, method]))
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT * FROM sim_orders WHERE customer_id=? AND request_id=?',
                                  (client['customer_id'], key)).fetchone()
            if existing:
                if existing['request_hash'] != signature:
                    raise SimulationConflict('Essa criação já foi usada com outros dados.')
                return self._view(db, existing)
            product = self.catalog.find_by_id(product_id)
            if product is None or not product.is_available or quantity > product.stock_quantity:
                raise SimulationConflict('Produto ou quantidade indisponível no snapshot.')
            promotions = self.catalog.active_promotions(product_id)
            quote = PaymentService.calculate_for_product(
                replace(product, price_brl=product.price_brl * quantity), promotions, pix=method == 'pix')
            total = quote.pix_price_brl if quote.pix_applied else quote.effective_price_brl
            result = db.execute('''INSERT INTO sim_orders(customer_id,request_id,request_hash,product_id,
                product_name,quantity,payment_method,total_brl,snapshot_at,state,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,'awaiting_payment',?)''',
                (client['customer_id'], key, signature, product_id, product.name, quantity, method,
                 str(total), product.snapshot.data_as_of.isoformat(), now().isoformat()))
            self._audit(db, result.lastrowid, 'created')
            row = db.execute('SELECT * FROM sim_orders WHERE id=?', (result.lastrowid,)).fetchone()
            return self._view(db, row)

    def transition(self, client, reference, action):
        order_id = self.parse(reference)
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM sim_orders WHERE id=? AND customer_id=?',
                             (order_id, client['customer_id'])).fetchone()
            if row is None:
                raise SimulationAccessError('Pedido de teste indisponível para este cliente.')
            if action == 'pay':
                if row['state'] == 'awaiting_payment':
                    db.execute("UPDATE sim_orders SET state='paid', paid_at=? WHERE id=?", (now().isoformat(), order_id))
                    self._audit(db, order_id, 'payment_approved')
            elif action == 'ship':
                if row['state'] == 'awaiting_payment':
                    raise SimulationConflict('Simule a aprovação do pagamento antes do despacho.')
                if row['state'] == 'paid':
                    code = generate_fake_tracking_code(f"simulation:{order_id}:{row['created_at']}")
                    db.execute("UPDATE sim_orders SET state='shipped', shipped_at=?, tracking_code=? WHERE id=?",
                               (now().isoformat(), code, order_id))
                    self._audit(db, order_id, 'dispatched')
                    db.execute('INSERT INTO sim_outbox(order_id, channel, message) VALUES (?,?,?)',
                               (order_id, 'WhatsApp simulado', f'Pedido fictício {reference} despachado. Rastreio fictício: {code}. Nenhuma mensagem real enviada.'))
            else:
                raise SimulationError('Ação de teste inválida.')
            row = db.execute('SELECT * FROM sim_orders WHERE id=?', (order_id,)).fetchone()
            return self._view(db, row)

    def get_status(self, order_reference, principal):
        if not isinstance(principal, AuthorizedPrincipal):
            return None
        try:
            order_id = self.parse(order_reference)
        except SimulationAccessError:
            return None
        with closing(self.connect()) as db:
            row = db.execute('SELECT * FROM sim_orders WHERE id=? AND customer_id=?',
                             (order_id, principal.customer_id)).fetchone()
            return self._view(db, row) if row else None

    def list_orders(self, client):
        with closing(self.connect()) as db:
            rows = db.execute('SELECT * FROM sim_orders WHERE customer_id=? ORDER BY id DESC LIMIT 30',
                              (client['customer_id'],)).fetchall()
            return [self._view(db, row) for row in rows]

    def post_sale(self, principal, reference, kind=None, description=None, request_id=None):
        if not isinstance(principal, AuthorizedPrincipal):
            raise SimulationAccessError('Pedido de teste indisponível para este cliente.')
        order_id = self.parse(reference)
        if kind is not None:
            if kind not in ('complaint', 'return'):
                raise SimulationError('Tipo de solicitação inválido.')
            if not isinstance(description, str) or not 1 <= len(description.strip()) <= 500:
                raise SimulationError('Informe uma descrição de até 500 caracteres.')
            if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
                raise SimulationError('Identificador da solicitação obrigatório.')
            description = description.strip()
        with closing(self.connect()) as db, db:
            if kind is not None:
                db.execute('BEGIN IMMEDIATE')
            owned = db.execute('SELECT id FROM sim_orders WHERE id=? AND customer_id=?',
                               (order_id, principal.customer_id)).fetchone()
            if owned is None:
                raise SimulationAccessError('Pedido de teste indisponível para este cliente.')
            if kind is not None:
                existing = db.execute('SELECT kind, description FROM sim_post_sale WHERE order_id=? AND request_id=?',
                                      (order_id, request_id)).fetchone()
                if existing and (existing['kind'], existing['description']) != (kind, description):
                    raise SimulationConflict('Identificador já utilizado com outros dados.')
                if not existing:
                    db.execute('INSERT INTO sim_post_sale(order_id,kind,description,request_id,created_at) VALUES (?,?,?,?,?)',
                               (order_id, kind, description, request_id, now().isoformat()))
            rows = db.execute('SELECT id, kind, description, created_at FROM sim_post_sale WHERE order_id=? ORDER BY id',
                              (order_id,)).fetchall()
            return [post_sale_view(row) for row in rows]

    def _audit(self, db, order_id, action):
        db.execute('INSERT INTO sim_order_events(order_id, action, occurred_at, trace_id) VALUES (?,?,?,?)',
                   (order_id, action, now().isoformat(), trace_id()))
        event('simulation_order', action=action, order_hash=fingerprint(self.reference(order_id)), simulated=True)

    def _view(self, db, row):
        tracking = None
        if row['tracking_code']:
            result = MockCorreiosTracking(observed_at=datetime.fromisoformat(row['shipped_at'])).track(row['tracking_code'])
            tracking = {'code': row['tracking_code'], 'status': result.status, 'source': result.source,
                        'observed_at': result.observed_at.isoformat()}
        audit = db.execute('SELECT action, occurred_at, trace_id FROM sim_order_events WHERE order_id=? ORDER BY id', (row['id'],)).fetchall()
        notification = db.execute('SELECT channel, message FROM sim_outbox WHERE order_id=?', (row['id'],)).fetchone()
        requests = db.execute('SELECT id, kind, description, created_at FROM sim_post_sale WHERE order_id=? ORDER BY id', (row['id'],)).fetchall()
        return {'simulated': True, 'order_reference': self.reference(row['id']), 'status': row['state'],
                'product_id': row['product_id'], 'product_name': row['product_name'], 'quantity': row['quantity'],
                'payment_method': row['payment_method'], 'total_brl': row['total_brl'], 'freight_included': False,
                'snapshot_at': row['snapshot_at'], 'tracking': tracking,
                'events': [dict(item) for item in audit], 'notification': dict(notification) if notification else None,
                'post_sale': [post_sale_view(item) for item in requests]}
