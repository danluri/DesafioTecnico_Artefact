---
title: 'Story 3.1 - Run and Verify the Assistant Offline'
type: 'feature'
created: '2026-11-03'
status: 'done'
baseline_commit: '904721e4e5a6a5d2100028353a9062b4406a3180'
route: 'dispatch'
review_loop_iteration: 0
context:
  - E:/Desafio tecnico Artefact/_bmad-output/implementation-artifacts/epic-3-context.md
  - E:/Desafio tecnico Artefact/_bmad-output/planning-artifacts/architecture/architecture-Desafio tecnico Artefact-2026-11-02/ARCHITECTURE-SPINE.md
  - E:/Desafio tecnico Artefact/_bmad-output/planning-artifacts/prds/prd-Desafio tecnico Artefact-2026-11-02/prd.md
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** Evaluators need to run and verify the trusted assistant reproducibly, but a passing happy-path command is not enough to prove privacy, failure handling, provider selection, Docker persistence, and deterministic domain behavior.

**Approach:** Establish a documented offline verification harness over the existing P0 services, SQLite volume, FakeLLM, tool/conversation scenarios, and sanitized observability. Add anonymized deterministic fixtures and executable scenario tests for catalog, policy, payment, order authorization, session isolation, prompt injection, unsupported actions, provider/tool failures, ambiguity, and partial results. Keep local-Llama validation opt-in and optional.

## Boundaries & Constraints

**Always:** Run without network credentials; use SQLite and synthetic/anonymized fixtures; verify all existing P0 behavior through stable commands; include snapshot/provenance/assumption visibility in demonstrations; assert no unauthorized private data, raw prompts, secrets, SQL, or provider payloads in outputs/events; validate FakeLLM and local-Llama factory contracts; verify Docker image/build/config, healthcheck, and named-volume database persistence when Docker is available; document unavailable optional integrations honestly.

**Never:** Never commit raw customer CSVs, internal PDFs, credentials, model caches, or generated databases; never make external services a test prerequisite; never label a readiness check as an interactive chat endpoint; never weaken domain tests because a provider is unavailable; never use live market/WhatsApp/MCP behavior to establish P0 correctness.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Verification |
|---|---|---|---|
| CLEAN_OFFLINE | Supported Python/uv environment with no credentials | Full deterministic suite runs | Exit zero, no network dependency |
| DOMAIN_REGRESSION | Catalog, policy, payment, promotion, order, and session fixtures | Existing acceptance behavior remains correct | Unit/integration assertions |
| SECURITY_SCENARIOS | Injection-shaped prompts, unknown tools, unauthorized orders, principal mismatch | Safe bounded response with no private disclosure | Scenario/security tests |
| FAILURE_SCENARIOS | Missing PDF, invalid source, provider/tool failure, timeout, partial result, expired session | Honest limitation or fresh context, never inferred success | Typed outcome assertions |
| PROVIDER_CONTRACT | FakeLLM selected; local-Llama configured or unavailable | Factory contract passes; unavailable local endpoint fails clearly | Contract test; local test opt-in |
| DOCKER_VOLUME | Docker image and named SQLite volume | Container reports readiness; reconnect/restart preserves schema/session state | Compose/build/runtime check when Docker exists |
| OPTIONAL_UNAVAILABLE | WhatsApp/market/MCP absent | Core P0 remains usable and status is transparent | Configuration/negative-path test |

## Code Map

- `tests/` -- consolidate or extend unit, integration, security, contract, and scenario coverage without duplicating domain rules.
- `tests/fixtures/` or existing temporary fixture helpers -- synthetic/anonymized deterministic inputs only.
- `README.md` -- document clean setup, Docker/volume commands, provider modes, verification commands, limitations, and executed demonstration transcripts.
- `Dockerfile`, `docker-compose.yml` -- keep reproducible P0 defaults, healthcheck, writable SQLite volume, and explicit optional local-Llama configuration.
- `src/emporio/runtime.py` -- keep readiness wiring deterministic and fail clearly on invalid configuration.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- record only confirmed verification limitations or post-P0 follow-ups.

## Tasks & Acceptance

**Execution:**
- [x] Add/organize deterministic anonymized fixtures and a single documented offline verification command.
- [x] Complete scenario/security/contract coverage for all Epic 1 and Epic 2 acceptance paths and provider/tool failures.
- [x] Verify sanitized observability and absence of unauthorized private data across outputs and stored events.
- [x] Validate Docker build/config, healthcheck, and SQLite named-volume persistence when the Docker daemon is available.
- [x] Update README with commands actually run, assumptions, limitations, provider modes, and three to five concise demonstration transcripts.

**Acceptance Criteria:**
- Given a clean supported environment without external credentials, when the documented offline verification command runs, then SQLite, FakeLLM, deterministic fixtures, and the complete P0 scenario suite pass.
- Given catalog, policy, payment, session, authorized-order, injection, ambiguity, unsupported-action, provider-failure, timeout, partial-result, and storage-failure scenarios, when tests execute, then expected safe outcomes pass and no unauthorized private data is disclosed.
- Given sanitized events are emitted, when logs are inspected by test assertions, then correlation/provider/tool outcome/duration/error data is present without raw prompts, PII, secrets, SQL, or full sensitive payloads.
- Given Docker is available, when the image is built and the compose service is started with its named volume, then readiness and healthcheck pass, SQLite is writable, and valid session data remains usable after container recreation.
- Given local-Llama or any optional integration is unavailable, when the P0 suite runs, then FakeLLM/core assistance remains available and the limitation is documented rather than hidden.

## Implementation Notes

Prefer one command sequence that can be copied into a clean checkout. Docker validation should use a temporary or named volume with explicit cleanup instructions and must not touch user data outside the project scope. Local-Llama tests remain opt-in based on `EMPORIO_LLM_PROVIDER` and endpoint configuration. The demonstration transcripts should use synthetic identifiers and show snapshot freshness, assumptions, safe refusal, and provider-unavailable behavior.

## Spec Change Log

Added deterministic fixtures, privacy/observability invariants, offline verification coverage, executable Docker persistence validation, and documented verification transcripts/limitations.

## Review Triage Log

`high (patch)` -- Added reusable privacy and observability assertions across failure, timeout, partial, and unauthorized paths.
`high (patch)` -- Verified Docker health and SQLite session persistence across container recreation with a unique project name and scoped cleanup.
`medium (patch)` -- Clarified transcripts as illustrative and documented Docker build/network and local-Llama limitations.

## Design Notes

This story verifies and documents the already-built P0 boundaries; it should not add WhatsApp, market comparison, MCP, production auth, or a new business rule. If Docker is present, run the real compose validation; if it is not, keep the contract test and record the environmental limitation explicitly.

## Verification

**Commands:**
- `python -m pytest -q` -- expected: complete offline suite passes.
- `uv run --with ruff ruff check src tests` -- expected: no lint findings.
- `python -m compileall -q src tests` -- expected: no syntax errors.
- `docker compose config` and `docker compose up --build -d` -- expected: valid config, healthy container, persistent SQLite volume when Docker is available.

</frozen-after-approval>
