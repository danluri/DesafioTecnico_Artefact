"""Infrastructure adapters for lexical policy retrieval."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen

from .policy import PolicyPassage, PolicySourceError, Provenance

_TOKEN_RE = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)
_SECTION_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s+(.+?)\s*$")
_STOPWORDS = {
    "a", "as", "ao", "aos", "com", "da", "das", "de", "do", "dos", "e", "em",
    "é", "na", "nas", "no", "nos", "o", "os", "para", "por", "que", "se", "um", "uma",
}
_INSTRUCTION_RE = re.compile(
    r"(?im)^\s*(?:system\s*:|assistant\s*:|user\s*:|"
    r"ignore\s+(?:all|previous)|disregard\s+(?:all|previous)).*$"
)
_MAX_INDEX_BYTES = 2_000_000
_MAX_PASSAGES_PER_BATCH = 128
_MIN_SEMANTIC_SIMILARITY = 0.25


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


def _semantic_evidence(text: str, *, max_chars: int = 800) -> str:
    """Return bounded sanitized evidence without requiring lexical query overlap."""

    compact = " ".join(sanitize_untrusted_text(text).split())
    return compact if len(compact) <= max_chars else compact[:max_chars] + "..."


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
        except Exception as exc:  # noqa: BLE001 - convert library failures to a domain error
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


class EmbeddingClient(Protocol):
    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        """Return one bounded embedding per input text."""


class OllamaEmbeddingClient:
    """Small stdlib-only client for a local Ollama-compatible embedding endpoint."""

    def __init__(self, base_url: str, model: str, *, timeout: float = 10.0) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("embedding base URL must use HTTP(S)")
        if not model or len(model) > 200:
            raise ValueError("embedding model is invalid")
        if not math.isfinite(timeout) or not 0.1 <= timeout <= 60:
            raise ValueError("embedding timeout must be between 0.1 and 60")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not texts or len(texts) > 128 or any(not text or len(text) > 12000 for text in texts):
            raise ValueError("embedding input is empty or exceeds bounds")
        payload = json.dumps({"model": self._model, "input": list(texts)}).encode("utf-8")
        request = Request(
            self._base_url + "/api/embed",
            data=payload,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                if getattr(response, "status", 200) != 200:
                    raise ValueError("embedding provider returned an unusable status")
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError("embedding provider response is too large")
            data = json.loads(raw.decode("utf-8"))
        except (OSError, URLError, TimeoutError, ValueError, UnicodeError, json.JSONDecodeError):
            raise ValueError("embedding provider is unavailable or malformed") from None
        return (
            _validate_embeddings(data.get("embeddings"), len(texts))
            if isinstance(data, dict)
            else ()
        )


def _validate_embeddings(value: object, expected: int) -> tuple[tuple[float, ...], ...]:
    if not isinstance(value, (list, tuple)) or len(value) != expected or not value:
        raise ValueError("embedding response has an invalid count")
    vectors: list[tuple[float, ...]] = []
    dimension: int | None = None
    for item in value:
        if not isinstance(item, (list, tuple)) or not 1 <= len(item) <= 8192:
            raise ValueError("embedding response has an invalid vector")
        vector = tuple(float(number) for number in item)
        if any(not math.isfinite(number) for number in vector):
            raise ValueError("embedding response contains a non-finite value")
        dimension = dimension or len(vector)
        if len(vector) != dimension or math.isclose(sum(number * number for number in vector), 0.0):
            raise ValueError("embedding response has inconsistent dimensions")
        vectors.append(vector)
    return tuple(vectors)


class SemanticPolicyRetriever:
    """Optional local semantic index with lexical fallback and provenance."""

    def __init__(
        self,
        passages: tuple[PolicyPassage, ...],
        client: EmbeddingClient,
        index_path: Path,
        source_fingerprint: str,
        fallback: LexicalPolicyRetriever,
        source_path: Path | None = None,
    ) -> None:
        self._passages = passages
        self._client = client
        self._index_path = index_path
        self._source_fingerprint = source_fingerprint
        self._fallback = fallback
        self._source_path = source_path.resolve() if source_path else None
        self._vectors = self._load_or_build()

    def _load_or_build(self) -> tuple[tuple[float, ...], ...]:
        try:
            if self._source_path and self._index_path.resolve() == self._source_path:
                raise ValueError("vector index cannot overwrite policy source")
            if self._index_path.is_file():
                if self._index_path.stat().st_size > _MAX_INDEX_BYTES:
                    raise ValueError("semantic policy index is too large")
                data = json.loads(self._index_path.read_text(encoding="utf-8"))
                if data.get("fingerprint") == self._source_fingerprint:
                    return _validate_embeddings(data.get("vectors"), len(self._passages))
            vectors: tuple[tuple[float, ...], ...] = ()
            for start in range(0, len(self._passages), _MAX_PASSAGES_PER_BATCH):
                batch = self._passages[start : start + _MAX_PASSAGES_PER_BATCH]
                vectors += self._client.embed(tuple(passage.text for passage in batch))
            _validate_embeddings(list(vectors), len(self._passages))
            self._index_path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(
                prefix="policy-index-", suffix=".tmp", dir=self._index_path.parent
            )
            os.close(fd)
            temporary_path = Path(temporary)
            try:
                temporary_path.write_text(
                    json.dumps({"fingerprint": self._source_fingerprint, "vectors": vectors}),
                    encoding="utf-8",
                )
                os.replace(temporary_path, self._index_path)
            finally:
                temporary_path.unlink(missing_ok=True)
            return vectors
        except Exception:  # noqa: BLE001 - semantic retrieval must never break lexical fallback
            raise ValueError("semantic policy index is unavailable") from None

    def search(self, query: str, *, limit: int = 5) -> tuple[PolicyPassage, ...]:
        if limit <= 0:
            return ()
        try:
            query_vector = _validate_embeddings(self._client.embed((query,)), 1)[0]
            scored = [
                (self._cosine(query_vector, vector), passage)
                for passage, vector in zip(self._passages, self._vectors)
            ]
            ranked = sorted(scored, key=lambda item: (-item[0], item[1].provenance.page))
            return tuple(
                PolicyPassage(
                    text=_semantic_evidence(passage.text),
                    provenance=passage.provenance,
                    score=max(1, int(round(score * 1000))),
                )
                for score, passage in ranked[:limit]
                if score >= _MIN_SEMANTIC_SIMILARITY
            )
        except Exception:  # noqa: BLE001 - provider failure falls back safely
            return self._fallback.search(query, limit=limit)

    @staticmethod
    def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
        if len(left) != len(right):
            raise ValueError("embedding dimensions do not match")
        denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
            sum(value * value for value in right)
        )
        return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0


def policy_retriever_from_path(
    path: Path, *, document_version: str = "local"
) -> LexicalPolicyRetriever:
    """Build the configured retriever, preserving lexical behavior by default."""

    lexical = PdfPolicyRetriever.from_path(path, document_version=document_version)
    enabled = os.getenv("EMPORIO_POLICY_SEMANTIC_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }
    if not enabled:
        return lexical
    try:
        client = OllamaEmbeddingClient(
            os.getenv("EMPORIO_POLICY_EMBEDDING_BASE_URL", "http://localhost:11434"),
            os.getenv("EMPORIO_POLICY_EMBEDDING_MODEL", "embeddinggemma"),
            timeout=float(os.getenv("EMPORIO_POLICY_EMBEDDING_TIMEOUT", "10")),
        )
        content_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        fingerprint = hashlib.sha256(
            f"{path.resolve()}:{content_digest}:{document_version}".encode()
        ).hexdigest()
        index_path = Path(os.getenv("EMPORIO_POLICY_VECTOR_INDEX", "data/policy-index.json"))
        return SemanticPolicyRetriever(
            tuple(lexical._passages), client, index_path, fingerprint, lexical, path
        )
    except Exception:  # noqa: BLE001 - disabled provider must preserve P0 behavior
        return lexical
