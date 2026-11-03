---
title: 'Story 2.3 - Execute Tools Safely and Handle Failures'
type: 'feature'
created: '2026-11-03'
status: 'done'
baseline_commit: '1a70d7a8cc392f390e09183afc01404a07c1f607'
route: 'dispatch'
review_loop_iteration: 0
context:
  - E:/Desafio tecnico Artefact/_bmad-output/implementation-artifacts/epic-2-context.md
  - E:/Desafio tecnico Artefact/_bmad-output/planning-artifacts/architecture/architecture-Desafio tecnico Artefact-2026-11-02/ARCHITECTURE-SPINE.md
  - E:/Desafio tecnico Artefact/_bmad-output/planning-artifacts/prds/prd-Desafio tecnico Artefact-2026-11-02/prd.md
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** A language model may request unsafe, unknown, malformed, repeated, or unauthorized operations, and provider/tool failures must not become fabricated answers or claims that an action completed.

**Approach:** Add a normalized `LLMPort` contract and `LLMFactory` that selects the deterministic `FakeLLM` or a configurable local-Llama adapter, an allowlisted schema-driven `ToolRegistry`, and a bounded orchestration service that validates arguments, checks the server principal, applies timeout and round budgets, and maps every internal failure to an honest Portuguese response. Existing deterministic catalog, policy, payment, session, and order services remain the only owners of facts.

## Boundaries & Constraints

**Always:** Execute only named registered tools; validate tool names and arguments before dispatch; authorize order tools with the server-provided `AuthorizedPrincipal`; enforce maximum rounds, calls, and per-tool timeout; normalize LLM messages/tool calls/results through `LLMPort`; create providers only through `LLMFactory`; support `FakeLLM` for deterministic offline tests and a local-Llama adapter for configured local validation; retain correlation/provider/tool outcome metadata without raw prompts, PII, SQL, or full payloads; return partial-data and unavailable-provider limitations explicitly; keep SQLite/session state usable inside Docker; preserve deterministic domain services outside the model.

**Never:** Never execute arbitrary SQL, shell commands, dynamic imports, URLs, code, or model-selected callables; never let the LLM author catalog/order/policy facts; never infer missing fields; never retry indefinitely; never expose stack traces, provider payloads, secrets, customer identifiers, or whether an unauthorized order exists; never require external credentials for P0.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| ALLOWED_TOOL | Known tool with valid schema and authorized context | Execute deterministic use case and return normalized result | Structured success event |
| UNKNOWN_TOOL | Model requests an unregistered name | Reject before execution | Honest unsupported response |
| INVALID_ARGS | Missing, extra, wrong-type, oversized, or injection-shaped arguments | Reject before repository/domain call | Typed validation limitation |
| UNAUTHORIZED_TOOL | Order tool without matching server principal | Refuse without existence disclosure | Safe authorization response |
| TIMEOUT_OR_PROVIDER_FAILURE | Tool/provider exceeds timeout or fails | Stop the round and explain unavailable information | No fabricated value/action |
| ROUND_BUDGET | Model repeatedly requests tools | Stop at configured maximum | Explicit limit response |
| PARTIAL_RESULT | Tool returns only some permitted fields | Mark response incomplete and identify unavailable fields | Never fill by inference |
| UNSUPPORTED_REQUEST | User asks for unrelated action or direct system access | Refuse or redirect clearly | No arbitrary execution |

## Code Map

- `src/emporio/llm.py` -- define normalized messages, tool calls/results, capabilities, `LLMPort`, deterministic `FakeLLM` scenarios, and the `LLMFactory` seam.
- `src/emporio/llm_local.py` -- implement the optional local-Llama adapter through a configurable local HTTP endpoint/model/timeout; no provider SDK or external credential is required.
- `src/emporio/tools.py` -- define tool schemas, typed registry, validation, authorization hooks, and safe result/error types.
- `src/emporio/conversation.py` -- implement bounded orchestration over `SessionService`, `LLMPort`, and `ToolRegistry`, including round/call/time budgets and safe fallbacks.
- `src/emporio/observability.py` -- emit sanitized structured outcome events with correlation ID, hashed session ID, tool/provider, duration, success, and error class only.
- `tests/test_tools.py`, `tests/test_conversation.py` -- cover allowlist, schema validation, authorization, prompt injection, timeout, provider failure, partial result, round budget, unsupported action, FakeLLM contract, and sanitized events.
- `README.md`, `Dockerfile`, `docker-compose.yml` -- document offline FakeLLM execution and retain the configured SQLite volume path without external credentials.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- record provider-specific or production-scale follow-ups only when confirmed by review.

## Tasks & Acceptance

**Execution:**
- [x] Define normalized LLM/provider contracts, `LLMFactory`, offline FakeLLM, and the optional local-Llama adapter.
- [x] Define and implement the allowlisted ToolRegistry with schema validation and server-side authorization.
- [x] Implement bounded ConversationService/orchestration with session context, timeout/call budgets, and typed safe fallbacks.
- [x] Add sanitized observability events and deterministic scenario/contract/security tests.
- [x] Update Docker/README commands so the P0 assistant path remains offline and SQLite-backed.

**Acceptance Criteria:**
- Given the model requests a known tool with valid arguments and authorization, when orchestration runs, then the deterministic use case executes and its normalized result is returned.
- Given an unknown tool, invalid arguments, arbitrary SQL/shell-shaped input, missing principal, or unauthorized order request, when orchestration runs, then execution is rejected before the unsafe boundary and the response does not disclose private existence data.
- Given a tool/provider failure, timeout, partial result, or unavailable capability, when a response is prepared, then the user receives an explicit limitation and no inferred value or completed-action claim.
- Given the model exceeds the configured round or tool-call budget, when orchestration continues, then further calls stop and the user receives a bounded honest response.
- Given the offline Docker/P0 suite runs, when FakeLLM, SQLite, and deterministic fixtures are used, then tests pass without network credentials and sanitized events contain no raw prompts, PII, secrets, SQL, or full payloads.
- Given a local-Llama endpoint and model are configured, when the factory selects the local provider, then the adapter satisfies the same normalized `LLMPort` contract; if the endpoint is unavailable, selection/execution fails clearly and FakeLLM remains selectable.

## Implementation Notes

Start with the existing deterministic services as registered tools: catalog search/detail, payment calculation, policy answer, and authorized order status. Tool schemas should expose only the minimum arguments needed by each use case. `LLMFactory` should accept explicit provider configuration such as `EMPORIO_LLM_PROVIDER=fake|local-llama`, `EMPORIO_LLAMA_BASE_URL`, `EMPORIO_LLAMA_MODEL`, and `EMPORIO_LLAMA_TIMEOUT`; Docker can reach a host Ollama service through an explicit configured URL. The local adapter is optional and must not become a P0 startup dependency. Session IDs and principal context come from the SessionService boundary, not from user text.

## Spec Change Log

Added `LLMFactory`, FakeLLM, optional local-Llama transport, allowlisted tools, bounded conversation orchestration, safe fallbacks, and Docker readiness wiring.

## Review Triage Log

`high (patch)` -- Preserved local-Llama tool-call continuity and JSON argument parsing across rounds.
`high (patch)` -- Enforced typed order principals, normalized session failures, and bounded read-only tool execution.
`medium (patch)` -- Added runtime readiness construction for the assistant path while keeping HTTP/CLI conversation delivery deferred.
`medium (defer)` -- Docker Compose execution and a real local-Llama endpoint require an environment with Docker/Ollama available; contract tests remain opt-in.

## Design Notes

The orchestrator must be able to return a structured outcome even when no model is available, so deterministic tools and safe refusals remain testable. Timeouts should be applied around tool execution without allowing a timed-out task to mutate state after the response boundary; where that guarantee cannot be made with the local adapter, the tool must be read-only or the limitation documented. Observability is an output contract, not a second message store.

## Verification

**Commands:**
- `python -m pytest -q` -- expected: existing, tool, conversation, security, and contract tests pass offline.
- `uv run --with ruff ruff check src tests` -- expected: no lint findings.
- `python -m compileall -q src tests` -- expected: no syntax errors.
- `docker compose config` -- expected: Docker configuration remains valid when Docker Compose is available.

</frozen-after-approval>
