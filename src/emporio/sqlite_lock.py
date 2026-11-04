"""Serialize complete repository operations on shared SQLite connections."""

from functools import wraps


def serialized(operation):
    @wraps(operation)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return operation(self, *args, **kwargs)
    return wrapped
