"""Domain types for traceable policy answers."""

from __future__ import annotations

from dataclasses import dataclass


class PolicyError(Exception):
    """Base error for policy retrieval and answer generation."""


class PolicySourceError(PolicyError):
    """The policy source cannot be read or parsed."""


class PolicyQueryError(PolicyError):
    """The customer query is invalid."""


@dataclass(frozen=True, slots=True)
class Provenance:
    source_file: str
    document_version: str
    page: int
    section: str


@dataclass(frozen=True, slots=True)
class PolicyPassage:
    text: str
    provenance: Provenance
    score: int = 0


@dataclass(frozen=True, slots=True)
class PolicyAnswer:
    text: str
    passages: tuple[PolicyPassage, ...]
    ambiguous: bool = False

    def render(self) -> str:
        """Render a safe customer-facing answer with compact provenance."""

        source_lines = [
            f"Fonte: {p.provenance.source_file}, página {p.provenance.page}, "
            f"seção {p.provenance.section}, versão {p.provenance.document_version}."
            for p in self.passages
        ]
        return f"{self.text.strip()}\n\n" + "\n".join(dict.fromkeys(source_lines))
