"""Request-scoped, privacy-conscious traces with bounded logs and SQLite history."""

from contextvars import ContextVar
from contextlib import closing, contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sqlite3
from threading import RLock
from time import monotonic, time
from uuid import uuid4, UUID

from .config import database_path


@dataclass
class TraceRun:
    enabled: bool = True
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    started: float = field(default_factory=monotonic)
    events: list = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)


_current = ContextVar('emporio_trace', default=None)
_suspended = ContextVar('emporio_trace_suspended', default=False)
_log_lock = RLock()


def fingerprint(value):
    return hashlib.sha256(str(value).encode('utf-8')).hexdigest()


def trace_id():
    run = _current.get()
    return run.trace_id if run else None


@contextmanager
def without_tracing():
    token = _suspended.set(True)
    try:
        yield
    finally:
        _suspended.reset(token)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname, 'trace_id': trace_id(),
            **getattr(record, 'structured', {'message': record.getMessage()}),
        }, ensure_ascii=False, default=str)


def runtime_logger():
    logger = logging.getLogger('emporio.local_llama')
    path = Path(os.getenv('EMPORIO_RUNTIME_LOG', 'data/emporio-runtime.log')).absolute()
    with _log_lock:
        if not any(getattr(h, '_emporio_path', None) == str(path) for h in logger.handlers):
            for previous in list(logger.handlers):
                if hasattr(previous, '_emporio_path'):
                    logger.removeHandler(previous)
                    previous.close()
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=3, encoding='utf-8')
            except OSError as exc:
                logger._emporio_file_error = repr(exc)
                handler = logging.StreamHandler()
            handler._emporio_path = str(path)
            handler.setFormatter(JsonFormatter())
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            logger.propagate = False
    return logger


class TraceStore:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv('EMPORIO_TRACE_DB') or database_path().with_name('observability.db'))

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=2)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.executescript('''
            CREATE TABLE IF NOT EXISTS traces (
                trace_id TEXT PRIMARY KEY, started REAL NOT NULL, finished REAL,
                outcome TEXT NOT NULL, duration_ms INTEGER, message_hash TEXT, session_hash TEXT
            );
            CREATE TABLE IF NOT EXISTS trace_events (
                id INTEGER PRIMARY KEY, trace_id TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
                timestamp REAL NOT NULL, payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS trace_events_lookup ON trace_events(trace_id, id);
            CREATE INDEX IF NOT EXISTS traces_started ON traces(started);
            CREATE INDEX IF NOT EXISTS traces_message ON traces(message_hash, started);
        ''')
        return db

    def begin(self, run, message_id):
        with closing(self.connect()) as db, db:
            days = max(1, int(os.getenv('EMPORIO_TRACE_RETENTION_DAYS', '7')))
            db.execute('DELETE FROM traces WHERE started < ?', (time() - days * 86400,))
            db.execute('INSERT INTO traces(trace_id, started, outcome, message_hash) VALUES (?, ?, ?, ?)',
                       (run.trace_id, time(), 'processing', fingerprint(message_id) if message_id else None))
        db.close()

    def append(self, run, event):
        with closing(self.connect()) as db, db:
            db.execute('INSERT INTO trace_events(trace_id, timestamp, payload) VALUES (?, ?, ?)',
                       (run.trace_id, time(), json.dumps(event, ensure_ascii=False, default=str)))
        db.close()

    def finish(self, run, outcome, session_id):
        with closing(self.connect()) as db, db:
            db.execute('UPDATE traces SET finished=?, outcome=?, duration_ms=?, session_hash=? WHERE trace_id=?',
                       (time(), outcome, int((monotonic()-run.started)*1000),
                        fingerprint(session_id)[:16] if session_id else None, run.trace_id))
        db.close()

    def get(self, identity):
        identity = str(UUID(identity))
        with closing(self.connect()) as db, db:
            row = db.execute('SELECT * FROM traces WHERE trace_id=?', (identity,)).fetchone()
            events = db.execute('SELECT payload FROM trace_events WHERE trace_id=? ORDER BY id', (identity,)).fetchall()
        db.close()
        return {**dict(row), 'events': [json.loads(e['payload']) for e in events]} if row else None

    def recent(self):
        with closing(self.connect()) as db, db:
            rows = db.execute('SELECT * FROM traces ORDER BY started DESC LIMIT 30').fetchall()
        db.close()
        return [dict(row) for row in rows]

    def by_message(self, identity):
        with closing(self.connect()) as db, db:
            row = db.execute('SELECT trace_id FROM traces WHERE message_hash=? ORDER BY started DESC LIMIT 1',
                             (fingerprint(identity),)).fetchone()
        db.close()
        return self.get(row['trace_id']) if row else None

    def metrics(self):
        with closing(self.connect()) as db, db:
            rows = db.execute("SELECT outcome, duration_ms FROM traces WHERE finished IS NOT NULL AND outcome NOT LIKE 'action_%' ORDER BY started DESC LIMIT 1000").fetchall()
        db.close()
        durations = sorted(r['duration_ms'] for r in rows)
        counts = {}
        for row in rows:
            counts[row['outcome']] = counts.get(row['outcome'], 0) + 1
        return {'sample_size': len(rows), 'outcomes': counts,
                'latency_ms': {'average': round(sum(durations)/len(durations)) if durations else 0,
                               'p50': durations[(len(durations)-1)//2] if durations else 0,
                               'p95': durations[max(0, (95*len(durations)+99)//100-1)] if durations else 0}}


def _store(operation, *args):
    try:
        return getattr(TraceStore(), operation)(*args)
    except (OSError, sqlite3.Error, ValueError):
        runtime_logger().warning('trace_storage_unavailable operation=%s', operation)
        return None


def diagnostic(**values):
    run = _current.get()
    if run:
        run.diagnostics.update(values)


def event(stage, status='success', duration_ms=0, **data):
    run = _current.get()
    if run is None or not run.enabled:
        return
    item = {'stage': stage, 'status': status, 'duration_ms': duration_ms,
            'offset_ms': int((monotonic()-run.started)*1000), 'data': data}
    if len(run.events) < 200:
        run.events.append(item)
        _store('append', run, item)
    runtime_logger().info(stage, extra={'structured': item})


@contextmanager
def action_trace(session_id=None):
    """Audit explicit development actions separately from conversation latency."""
    run = TraceRun(enabled=os.getenv('EMPORIO_TRACE_ENABLED', 'true').lower() != 'false')
    token = _current.set(run)
    if run.enabled:
        _store('begin', run, None)
    try:
        yield run
    except Exception as exc:
        event('simulation_action', status='failure', error_class=type(exc).__name__)
        if run.enabled:
            _store('finish', run, 'action_failure', session_id)
        raise
    else:
        event('simulation_action', simulated=True)
        if run.enabled:
            _store('finish', run, 'action_success', session_id)
    finally:
        _current.reset(token)


def traced_request(operation):
    @wraps(operation)
    def wrapped(self, text, **kwargs):
        if _suspended.get():
            return operation(self, text, **kwargs)
        run = TraceRun(enabled=os.getenv('EMPORIO_TRACE_ENABLED', 'true').lower() != 'false')
        token = _current.set(run)
        if run.enabled:
            _store('begin', run, kwargs.get('message_id'))
        event('message_received', characters=len(text))
        try:
            result = operation(self, text, **kwargs)
            if not run.enabled:
                return replace(result, diagnostics=dict(run.diagnostics))
            event('response_ready', status=result.outcome, persistence=result.persistence.value)
            _store('finish', run, result.outcome, result.session_id)
            return replace(result,
                           trace={'trace_id': run.trace_id, 'outcome': result.outcome,
                                  'duration_ms': int((monotonic()-run.started)*1000),
                                  'events': list(run.events)}, diagnostics=dict(run.diagnostics))
        except Exception as exc:
            event('request_error', status='failure', error_class=type(exc).__name__)
            if run.enabled:
                _store('finish', run, 'failure', None)
            raise
        finally:
            _current.reset(token)
    return wrapped
