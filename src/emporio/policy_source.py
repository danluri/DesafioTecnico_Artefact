"""Infrastructure adapters for lexical policy retrieval."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .policy import PolicyPassage, PolicySourceError, Provenance

_TOKEN_RE = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)
_SECTION_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s+(.+?)\s*$")
_STOPWORDS = {
    "a", "as", "ao", "aos", "com", "da", "das", "de", "do", "dos", "e", "em",
    "é", "na", "nas", "no", "nos", "o", "os", "para", "por", "que", "se", "um", "uma",
}
_INSTRUCTION_RE = re.compile(
    r"(?im)^\s*(?:system\s*:|assistant\s*:|user\s*:|ignore\s+(?:all|previous)|disregard\s+(?:all|previous)).*$"
)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).lower()


def _terms(value: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall(_normalize(value)) if token not in _STOPWORDS}


def sanitize_untrusted_text(value: str) -> str:
    """Remove instruction-shaped lines from text shown as policy evidence."""

    return _INSTRUCTION_RE.sub("", value).strip()


def _compact_evidence(text: str, query: str, *, max_chars: int = 800) -> str:
    """Return a bounded excerpt around the first matching query term."""

    compact = " ".join(sanitize_untrusted_text(text).split())
    if len(compact) <= max_chars:
        return compact
    query_terms = _terms(query)
    normalized = _normalize(compact)
    positions = [normalized.find(term) for term in query_terms if normalized.find(term) >= 0]
    start = max(positions, default=0)
    left = max(0, start - max_chars // 3)
    excerpt = compact[left : left + max_chars]
    if left:
        excerpt = "…" + excerpt
    if left + max_chars < len(compact):
        excerpt += "…"
    return excerpt


class LexicalPolicyRetriever:
    """Small deterministic lexical index for a bounded policy corpus."""

    def __init__(self, passages: tuple[PolicyPassage, ...], *, minimum_score: int = 1) -> None:
        self._passages = passages
        self._minimum_score = minimum_score

    def search(self, query: str, *, limit: int = 5) -> tuple[PolicyPassage, ...]:
        query_terms = _terms(query)
        if not query_terms or limit <= 0:
            return ()

        ranked: list[PolicyPassage] = []
        for passage in self._passages:
            passage_terms = _terms(passage.text + " " + passage.provenance.section)
            score = len(query_terms & passage_terms)
            if score >= self._minimum_score:
                ranked.append(
                    PolicyPassage(
                        text=_compact_evidence(passage.text, query),
                        provenance=passage.provenance,
                        score=score,
                    )
                )
        ranked.sort(key=lambda item: (-item.score, item.provenance.page, item.provenance.section))
        return tuple(ranked[:limit])


class PdfPolicyRetriever(LexicalPolicyRetriever):
    """Extract one bounded, provenance-bearing passage per PDF page."""

    @classmethod
    def from_path(cls, path: Path, *, document_version: str = "local") -> PdfPolicyRetriever:
        if not path.is_file():
            raise PolicySourceError(f"Policy source not found: {path}")
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            passages: list[PolicyPassage] = []
            for page_number, page in enumerate(reader.pages, start=1):
                text = (page.extract_text() or "").strip()
                if not text:
                    continue
                section_match = next(
                    (match for line in text.splitlines() if (match := _SECTION_RE.match(line))),
                    None,
                )
                section = section_match.group(1) if section_match else f"page-{page_number}"
                passages.append(
                    PolicyPassage(
                        text=text,
                        provenance=Provenance(
                            source_file=path.name,
                            document_version=document_version,
                            page=page_number,
                            section=section,
                        ),
                    )
                )
            if not passages:
                raise PolicySourceError("Policy source contains no extractable text")
            return cls(tuple(passages))
        except PolicySourceError:
            raise
        except Exception as exc:  # noqa: BLE001 - adapter converts library failures to a domain error
            raise PolicySourceError(f"Unable to read policy source: {path}") from exc


class TextPolicyRetriever(LexicalPolicyRetriever):
    """Fixture-friendly retriever used by offline tests."""

    @classmethod
    def from_text(cls, text: str, *, source_file: str = "fixture.txt") -> TextPolicyRetriever:
        passages = tuple(
            PolicyPassage(
                text=chunk.strip(),
                provenance=Provenance(
                    source_file=source_file,
                    document_version="fixture",
                    page=index,
                    section=f"fixture-{index}",
                ),
            )
            for index, chunk in enumerate(text.split("\n---\n"), start=1)
            if chunk.strip()
        )
        return cls(passages)
