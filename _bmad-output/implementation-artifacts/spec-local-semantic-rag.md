---
title: 'Add optional local semantic retrieval for store policies'
type: 'feature'
created: '2026-11-03'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '697d31e'
context: []
---

<frozen-after-approval>

## Intent

**Problem:** Policy answers currently use bounded lexical retrieval. This is free and safe, but it misses semantically equivalent questions that use different words from the PDF.

**Approach:** Add an optional local semantic retriever that obtains embeddings from a local Ollama-compatible endpoint and searches a persisted local vector index. Keep the existing lexical retriever as the default and as a safe fallback when the embedding provider is disabled, unavailable, or returns malformed data. Preserve page/section provenance, bounded results, prompt-injection sanitization, and the existing `PolicyRetriever` interface.

**Always:** Keep provider calls opt-in, configurable by environment variables, network-free in the default Docker/test path, deterministic when lexical fallback is used, and explicit about simulated/local behavior. Do not send policy text to a hosted service by default. Rebuild the index when the source document version changes.

**Never:** Make semantic retrieval a required startup dependency, remove lexical retrieval, expose raw embeddings, accept unbounded provider responses, or let similarity results override policy/service authorization rules.

</frozen-after-approval>

## Code Map

- `src/emporio/policy_source.py` -- preserve `PdfPolicyRetriever` and add the optional semantic index/retriever beside the lexical implementation; reuse PDF passage extraction and sanitization.
- `src/emporio/ports.py` -- keep the existing `PolicyRetriever.search()` contract; no consumer should depend on a concrete vector backend.
- `src/emporio/service.py` -- no policy authority changes; continue filtering bounded passages and rendering provenance.
- `src/emporio/config.py`, `src/emporio/runtime.py`, `docker-compose.yml` -- add explicit opt-in configuration without enabling network access by default.
- `pyproject.toml` -- avoid mandatory heavyweight ML dependencies; use the standard library HTTP client for Ollama embeddings and a small persisted local index implementation.
- `tests/test_policy_source.py` and new semantic tests -- cover cosine ranking, persistence/version invalidation, malformed provider responses, fallback, bounded results, provenance, and disabled mode.
- `README.md` -- document Ollama model/base URL variables, Docker usage, local-only behavior, and lexical fallback.

## Tasks & Acceptance

**Execution:**
- [x] Implement a bounded local embedding client and persisted semantic index with configurable path/model/base URL.
- [x] Compose semantic retrieval with lexical fallback while preserving sanitization and provenance.
- [x] Add configuration, Docker documentation, and offline tests using a fake embedding client; no test may require Ollama.

**Acceptance Criteria:**
- Given semantic mode is disabled or unavailable, policy answers behave exactly as the current lexical path.
- Given a fake embedding client and a policy PDF, semantically similar wording ranks the relevant passage and keeps its page/section provenance.
- Given a changed document version, stale vectors are not reused silently.
- Given malformed, oversized, or incomplete embedding responses, retrieval fails safely to lexical search.
- Given Docker defaults, startup and the complete offline test suite require no external service or credential.

## Implementation Notes

- Recommended first backend: Ollama-compatible embeddings plus a small JSON/SQLite-backed vector index, avoiding a mandatory FAISS/Chroma dependency in the base image.
- The first model is configuration-only; the implementation must not hard-code a paid provider or claim a hosted free tier.
- The lexical retriever remains the P0 production default until semantic quality is evaluated against representative Portuguese policy questions.
- Implemented `OllamaEmbeddingClient`, `SemanticPolicyRetriever`, and `policy_retriever_from_path`; semantic mode is enabled only with `EMPORIO_POLICY_SEMANTIC_ENABLED`.
- The persisted JSON index is fingerprinted by document path, size, modification time, and version; invalid provider responses fall back to lexical retrieval.
- Verification: `python -m pytest -q` passed 127 tests with 1 skipped; `python -m compileall -q src tests` passed. Ruff was previously available and clean, while the current environment cannot fetch its package because network/cache access is restricted.

## Open Questions

None. The backend and model are intentionally configurable implementation details; the approved behavior is optional local semantic retrieval with lexical fallback.

## Review Triage Log

- blind-hunter / batch limit: `medium` fixed in `src/emporio/policy_source.py`; corpus embedding now uses bounded batches of 128 passages.
- blind-hunter / arbitrary positive similarity: `medium` fixed; semantic results require a minimum cosine similarity and otherwise produce no semantic evidence.
- blind-hunter / semantic excerpt selection: `medium` fixed; semantic results use bounded sanitized evidence without requiring lexical query overlap.
- blind-hunter / unbounded persisted index: `medium` fixed; index files are size-limited and vectors remain dimension/count validated.
- blind-hunter / stale timestamp fingerprint: `medium` fixed; the fingerprint includes the policy file content digest and document version.
- blind-hunter / repeated full-corpus retry: `medium` fixed; indexing is batched and written atomically, with safe lexical fallback on failure.
- blind-hunter / missing regression tests: `medium` fixed for the relevant paths with tests covering malformed initialization, cache reuse, CLI selection, HTTP contract, and sanitization.
- blind-hunter / README provider setup: `low` fixed by documenting `ollama pull embeddinggemma` and the `/api/embed` contract.
- blind-hunter / centralized configuration: `false`; semantic retrieval currently has one CLI factory boundary and the environment variables are intentionally local to that optional adapter.
- edge-case-hunter / malformed query vector: `high` fixed by validating the query embedding before cosine calculation and falling back lexically.
- edge-case-hunter / oversized index: `medium` fixed with a 2 MB persisted-index bound before parsing.
- edge-case-hunter / index path colliding with source: `high` fixed by rejecting the same resolved path and preserving lexical retrieval.
- verification-gap / semantic CLI path: `medium` fixed with an enabled-mode CLI test.
- verification-gap / persisted index reuse: `medium` fixed by asserting a same-fingerprint second construction does not re-embed.
- verification-gap / Ollama HTTP contract: `medium` fixed with an offline mocked HTTP response test; live Ollama remains intentionally unrequired.
- verification-gap / semantic sanitization: `medium` fixed with an instruction-shaped semantic passage test.

