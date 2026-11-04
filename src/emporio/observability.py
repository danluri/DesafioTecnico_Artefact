"""Sanitized events for correlation without creating a second message store."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from time import monotonic
from typing import Callable


@dataclass(frozen=True, slots=True)
class SafetyEvent:
    correlation_id: str
    session_hash: str
    provider: str
    tool: str | None
    duration_ms: int
    outcome: str
    error_class: str | None = None


class Observability:
    def __init__(self, sink: Callable[[SafetyEvent], None] | None = None) -> None:
        self.events: list[SafetyEvent] = []
        self._sink = sink

    @staticmethod
    def hash_session(session_id: object) -> str:
        return hashlib.sha256(str(session_id).encode("utf-8")).hexdigest()[:16]

    def emit(self, event: SafetyEvent) -> None:
        self.events.append(event)
        if len(self.events) > 2000:
            del self.events[:-2000]
        if self._sink:
            self._sink(event)


def elapsed_ms(start: float) -> int:
    return max(0, int((monotonic() - start) * 1000))
