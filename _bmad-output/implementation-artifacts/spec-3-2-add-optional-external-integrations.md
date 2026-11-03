---
title: 'Story 3.2 - Add Optional External Integrations'
type: 'feature'
created: '2026-11-03'
status: 'done'
baseline_commit: 'f40654f62b62d48439ec095ed577826de4893b80'
route: 'dispatch'
review_loop_iteration: 0
context:
  - E:/Desafio tecnico Artefact/_bmad-output/implementation-artifacts/epic-3-context.md
  - E:/Desafio tecnico Artefact/_bmad-output/planning-artifacts/architecture/architecture-Desafio tecnico Artefact-2026-11-02/ARCHITECTURE-SPINE.md
  - E:/Desafio tecnico Artefact/_bmad-output/planning-artifacts/prds/prd-Desafio tecnico Artefact-2026-11-02/prd.md
  - E:/Desafio tecnico Artefact/_bmad-output/planning-artifacts/prds/prd-Desafio tecnico Artefact-2026-11-02/addendum.md
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** The assistant must eventually support the store's primary remote channel and useful external capabilities without duplicating business rules, exposing private data, or making P0 dependent on credentials and third-party availability.

**Approach:** Add isolated ports/adapters for WhatsApp, Correios delivery tracking, market comparison, and MCP. Each adapter normalizes transport/provider data into existing application contracts, is selected by explicit configuration, and fails closed to an honest Portuguese limitation. WhatsApp remains the primary remote channel; Correios is the policy-aligned source for live tracking when configured and authorized; market offers remain separate from official prices; MCP reuses existing use cases.

## Boundaries & Constraints

**Always:** Route WhatsApp messages through `ConversationService`; validate webhook shape, signature/token, normalization, and idempotency; keep credentials in environment variables; require `AuthorizedPrincipal` before Correios tracking lookup; use the official Correios adapter only through a typed port and preserve provider status/provenance/freshness; never expose a tracking code or status to an unauthorized customer; keep P0 snapshot order status available if Correios fails; return exact-product market offers with retailer, URL, observed date, condition, and match information; expose only selected MCP operations over existing use cases; feature-flag every optional adapter and keep Docker startup usable without them.

**Never:** Never claim real Meta or Correios delivery without configured credentials and a successful provider response; never treat a tracking code, phone, name, or order ID from message text as authentication; never overwrite official product prices with market observations; never let arbitrary MCP/WhatsApp input choose imports, SQL, shell commands, or provider URLs; never make network access required for offline tests.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| WHATSAPP_VALID | Verified webhook with new message | Normalize and route through shared conversation service | Provider response is isolated |
| WHATSAPP_DUPLICATE | Same message/event ID repeated | Process at most once and return idempotent acknowledgement | No duplicate assistant action |
| WHATSAPP_INVALID | Bad signature/token/schema | Reject without routing or leaking details | Safe transport error |
| CORREIOS_AUTHORIZED | Authorized owner with configured tracking code | Return provider status, observation time, and clear live-provider provenance | No snapshot/live confusion |
| CORREIOS_UNAVAILABLE | Provider timeout, invalid code, missing credentials, or partial response | Preserve snapshot order status and explain live tracking unavailable | No invented status |
| CORREIOS_UNAUTHORIZED | Principal absent or does not own order | Refuse without revealing existence/tracking data | Same non-enumerating outcome |
| MARKET_EXACT | Exact product match with enough independent offers | Return separate External Offers with provenance | Official price unchanged |
| MARKET_MISMATCH | Variant/condition mismatch or insufficient offers | Reject or label as incomplete | No misleading comparison |
| MCP_SUPPORTED | Selected operation requested through MCP | Reuse same authorized use case and safe output | Unsupported operation rejected |
| OPTIONAL_FAILURE | Any adapter disabled or unavailable | Core P0 remains operational | Honest Portuguese limitation |

## Code Map

- `src/emporio/whatsapp.py` -- define normalized webhook/message contracts, verification, deduplication, and adapter port.
- `src/emporio/correios.py` -- define typed tracking port/adapter, explicit environment configuration, timeout, provider normalization, provenance, and safe errors.
- `src/emporio/market.py` -- define External Offer value objects and exact-match/provider boundary without touching official catalog rows.
- `src/emporio/mcp.py` -- expose a small allowlisted adapter over existing use cases and authorization.
- `src/emporio/conversation.py`, `src/emporio/order_service.py` -- reuse existing boundaries; do not duplicate rules in adapters.
- `tests/test_integrations.py` -- contract tests using fake providers for WhatsApp, Correios, market, and MCP, including disabled/failure/security paths.
- `README.md`, `Dockerfile`, `docker-compose.yml` -- document optional environment variables, feature flags, and P0-safe defaults.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- record provider certification, production credentials, and transport-specific follow-ups.

## Tasks & Acceptance

**Execution:**
- [x] Define optional adapter ports, configuration, typed provider results, and safe failure mapping.
- [x] Implement WhatsApp normalization, verification, deduplication, and shared ConversationService routing.
- [x] Implement the Correios tracking adapter with authorized-order boundary, timeout, provenance, and no-P0-dependency behavior.
- [x] Implement provenance-bearing market offers and selected MCP operations over existing use cases.
- [x] Add fake-provider contract/security tests and Docker configuration examples without requiring credentials.
- [x] Update README with WhatsApp as primary remote channel and Correios tracking caveats.

**Acceptance Criteria:**
- Given WhatsApp is enabled and a webhook is valid, when a new message arrives, then it is normalized, deduplicated, and routed through the shared ConversationService; invalid or duplicate webhooks do not trigger duplicate actions.
- Given an authorized order owner and configured Correios adapter, when tracking is requested, then the response contains only normalized provider status with observation/provenance and does not replace snapshot order facts.
- Given Correios credentials are absent, the code is unavailable, the tracking code is invalid, or the provider times out, when live tracking is requested, then the system reports that live tracking is unavailable and still preserves authorized snapshot status.
- Given an unauthorized principal requests tracking, when any identifier is supplied, then no tracking status, existence signal, or private order detail is returned.
- Given market comparison or MCP is disabled, unavailable, mismatched, or unsupported, when the assistant is used, then P0 catalog, policy, payment, session, and order behavior remains available and the limitation is explicit.
- Given optional adapter contract tests run offline, when fake providers are used, then all security, provenance, timeout, deduplication, and failure cases pass without network credentials.

## Implementation Notes

The Correios integration is the primary point of attention from the store policy and should be implemented behind a `CorreiosTrackingPort`, not embedded in order or conversation logic. The current official Rastro documentation describes a Bearer-token request to `/srorastro/v1/objetos/{codigoObjeto}` and warns that API queries may be restricted to objects linked to the sender's contract; the adapter must therefore keep the base URL and token explicit and never claim that a public tracking lookup is universally available. Reserve `EMPORIO_CORREIOS_ENABLED`, `EMPORIO_CORREIOS_BASE_URL`, `EMPORIO_CORREIOS_TOKEN`, and `EMPORIO_CORREIOS_TIMEOUT`; do not guess a production host. WhatsApp variables remain separate (`EMPORIO_WHATSAPP_ENABLED`, webhook verify token, access token, phone-number ID, API base URL). All real delivery claims require an integration test with valid credentials.

## Spec Change Log

Added Correios Rastro, signed WhatsApp webhook, durable idempotency seam, exact market offers, MCP allowlist, feature flags, and safe provider failures.

## Review Triage Log

`high (patch)` -- Restricted Correios Bearer delivery to approved HTTPS hosts and validated the official response envelope/object code.
`high (patch)` -- Required WhatsApp signature verification, atomic deduplication, and thread-safe idempotency storage.
`medium (defer)` -- Live credential certification for Correios/Meta and production transport exposure remain environment-dependent.
`medium (defer)` -- WhatsApp multi-message batches are rejected explicitly rather than partially processed.

## Design Notes

Correios live tracking supplements the authorized snapshot; it never changes the order's persisted status. The adapter should return a typed `TrackingResult` with status, observed time, source, and optional public carrier message, while redacting provider payloads and tracking identifiers from logs. If the policy requires a specific endpoint or authentication mode not yet confirmed, keep that detail as an implementation question and do not guess it.

## Verification

**Commands:**
- `python -m pytest -q` -- expected: core and optional adapter contract tests pass offline.
- `uv run --with ruff ruff check src tests` -- expected: no lint findings.
- `python -m compileall -q src tests` -- expected: no syntax errors.
- `docker compose config` -- expected: optional environment variables do not make P0 startup fail.

</frozen-after-approval>
