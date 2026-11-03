"""Application service for safe policy answers."""

from __future__ import annotations

import re

from .policy import PolicyAnswer, PolicyQueryError
from .ports import PolicyRetriever

_PHONE_RE = re.compile(r"\(\d{2}\)\s*\d{4,5}-\d{4}")


class PolicyService:
    def __init__(self, retriever: PolicyRetriever, *, minimum_score: int = 1) -> None:
        self._retriever = retriever
        self._minimum_score = minimum_score

    def answer(self, query: str) -> PolicyAnswer:
        if not query or not query.strip():
            raise PolicyQueryError("A policy question cannot be empty")

        passages = self._retriever.search(query, limit=5)
        passages = tuple(passage for passage in passages if passage.score >= self._minimum_score)
        if not passages:
            return PolicyAnswer(
                text=(
                    "Não encontrei evidência suficiente no manual da loja para responder com "
                    "segurança. "
                    "Confirme esta informação com a equipe da loja."
                ),
                passages=(),
            )

        phones = {
            phone.replace(" ", "")
            for passage in passages
            for phone in _PHONE_RE.findall(passage.text)
        }
        if phones and len(phones) > 1:
            return PolicyAnswer(
                text=(
                    "Encontrei informações de contato divergentes no manual da loja: "
                    + ", ".join(sorted(phones))
                    + ". Confirme com a equipe qual número está ativo."
                ),
                passages=passages,
                ambiguous=True,
            )

        best = passages[:1]
        return PolicyAnswer(text=best[0].text, passages=best)
