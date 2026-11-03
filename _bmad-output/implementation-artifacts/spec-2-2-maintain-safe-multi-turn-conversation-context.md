---
title: 'Story 2.2 - Maintain Safe Multi-Turn Conversation Context'
type: 'feature'
created: '2026-11-03'
status: 'done'
baseline_commit: '7f7a6205c54a0faf4844f35699f30ca568586d8c'
route: 'dispatch'
review_loop_iteration: 0
context:
  - E:/Desafio tecnico Artefact/_bmad-output/implementation-artifacts/epic-2-context.md
  - E:/Desafio tecnico Artefact/_bmad-output/planning-artifacts/architecture/architecture-Desafio tecnico Artefact-2026-11-02/ARCHITECTURE-SPINE.md
  - E:/Desafio tecnico Artefact/_bmad-output/planning-artifacts/prds/prd-Desafio tecnico Artefact-2026-11-02/prd.md
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** Customers need follow-up questions to retain useful product or policy context, but conversation history and authorization state must never cross session or customer boundaries.

**Approach:** Create a deterministic Session domain and SQLite-backed `SessionRepository` with opaque internal session IDs. A `SessionService` owns creation, append, bounded retrieval, principal binding, and expiration behavior. It stores normalized message envelopes rather than provider-specific payloads and returns a fresh safe context when storage is unavailable or a session has expired.

## Boundaries & Constraints

**Always:** Bind a session to the server-established principal context at creation; keep session IDs opaque and independent from customer IDs; bound history by a documented message count and content size; preserve message role and text needed for follow-ups; use parameterized SQL and atomic writes; enforce expiry on every read/write; isolate sessions even for the same principal; sanitize stored/displayed content and retain only application context needed by later stories; expose typed repository/service errors; run offline with SQLite and synthetic fixtures; keep the SQLite path configurable for Docker and support a mounted persistent volume without relying on a host-only path.

**Never:** Never use customer IDs, phone numbers, e-mails, order IDs, or names as public session IDs; never accept identity claims from message text as authorization; never restore expired or inaccessible private history; never share history between sessions; never persist raw provider payloads, prompts, tool arguments, PII, or stack traces; never introduce LLM/provider/session orchestration into this story.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| NEW_SESSION | Valid opaque request and optional principal | Return unique session ID with empty bounded history and bound authorization context | Deterministic creation |
| FOLLOW_UP | Active session with messages | Append normalized message and return only the bounded current history in order | Older messages are evicted by policy |
| SESSION_ISOLATION | Two sessions, same or different principals | Each session returns only its own messages and binding | Never fall back to another session |
| PRINCIPAL_MISMATCH | Existing session read/write with a different principal | Refuse access without returning history | Safe authorization error |
| EXPIRED_SESSION | Current time past expiry | Return fresh empty context; do not restore old messages or private binding | Typed expired outcome |
| STORAGE_FAILURE | Repository unavailable or malformed stored row | Return fresh safe context and a recoverable service outcome | No stale/private fallback |
| INVALID_MESSAGE | Empty, oversized, unsupported role, or control-heavy content | Reject without mutating session state | Typed validation error |

## Code Map

- `src/emporio/session.py` -- define opaque `SessionId`, normalized message roles/envelopes, session context, limits, expiry, and typed errors.
- `src/emporio/session_repository.py` -- define the `SessionRepository` port for isolated create/read/append/expire operations.
- `src/emporio/session_service.py` -- own session lifecycle, principal binding, bounded history, expiry, and safe failure policy.
- `src/emporio/session_sqlite.py` -- implement parameterized SQLite storage with opaque IDs, atomic append, schema constraints, and container-safe path initialization.
- `src/emporio/config.py` or `src/emporio/cli.py` -- resolve the database path from explicit configuration/environment so Docker can mount persistent storage without changing domain code.
- `Dockerfile`, `docker-compose.yml`, or deployment documentation if present -- document the writable SQLite volume and startup path without introducing external credentials.
- `tests/test_session.py` -- cover continuity, isolation, principal mismatch, expiration, bounds, invalid input, storage failure, and no-PII persistence.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- record only review-confirmed follow-up work.

## Tasks & Acceptance

**Execution:**
- [x] Define normalized session/message value objects, limits, opaque IDs, and typed errors.
- [x] Define the repository port and SQLite schema with atomic bounded writes.
- [x] Implement the session service with server-principal binding, isolation, expiration, and fail-safe storage handling.
- [x] Add deterministic tests for all matrix cases and verify stored rows do not contain customer identity fields or provider payloads.

**Acceptance Criteria:**
- Given an active session with prior product or policy messages, when a follow-up is appended, then the service returns the relevant bounded history in order.
- Given two sessions belong to the same or different principals, when either session is read or updated, then neither can access the other's messages or authorization context.
- Given a session is expired or storage is unavailable, when a message arrives, then the service creates or returns a fresh safe context and does not restore stale private information.
- Given a message has an unsupported role, empty content, control characters, or exceeds the configured bound, when it is appended, then the session remains unchanged and a typed validation outcome is returned.
- Given the offline test suite runs, when session scenarios execute, then they pass with temporary SQLite, synthetic fixtures, and no network credentials or LLM provider.
- Given the application runs in Docker with a configured writable database path, when the container restarts with the same mounted volume, then the SQLite schema and valid session data remain usable without requiring a host filesystem path.

## Implementation Notes

The first delivery surface is an application/service contract, not a chat endpoint. Use a cryptographically random UUID for the opaque public session identifier, while keeping principal binding internal to the service/repository contract. A fixed default history limit of 20 messages and 8,000 characters per message is acceptable unless the implementation discovers a concrete constraint; expose limits as configuration rather than hard-code them into delivery code. Docker should pass an explicit SQLite path such as `/data/emporio.db` and mount `/data` as a persistent volume; the default local path remains suitable for tests.

## Spec Change Log

Added SQLite-backed bounded sessions, Docker volume configuration, typed principal binding, HMAC storage isolation, expiry cleanup, and recoverable storage outcomes.

## Review Triage Log

`high (patch)` -- Replaced arbitrary string principals with server-established `AuthorizedPrincipal` values and keyed HMAC bindings.
`high (patch)` -- Expired-session cleanup, malformed-storage handling, and storage-failure invalidation now fail closed.
`medium (patch)` -- Docker runs a storage-ready process with `/data` persistence and production secret configuration checks.
`medium (defer)` -- Full container restart integration requires Docker Compose availability in the execution environment; the SQLite reconnect contract is covered offline.

## Design Notes

Session expiry is checked against an injected clock so tests remain deterministic. The repository should treat a principal mismatch and missing session as a safe access failure, while the service maps expired or unavailable storage to a fresh context without exposing whether old data existed. Later `ConversationService` work can consume this contract without allowing channels or LLM providers to own state.

## Verification

**Commands:**
- `uv run pytest -q` -- expected: existing suite and session tests pass offline.
- `uv run --with ruff ruff check src tests` -- expected: no lint findings.
- `python -m compileall -q src tests` -- expected: no syntax errors.

</frozen-after-approval>
