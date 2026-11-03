"""Ports used by the policy application service."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .policy import PolicyPassage


class PolicyRetriever(Protocol):
    def search(self, query: str, *, limit: int = 5) -> tuple[PolicyPassage, ...]:
        """Return bounded, provenance-bearing passages for a query."""


class PolicySourceLoader(Protocol):
    @classmethod
    def from_path(cls, path: Path, *, document_version: str) -> PolicyRetriever:
        """Create a retriever from a local policy source."""
