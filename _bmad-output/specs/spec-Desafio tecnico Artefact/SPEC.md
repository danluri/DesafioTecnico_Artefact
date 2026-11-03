---
id: SPEC-Desafio-tecnico-Artefact
companions:
  - capabilities.md
  - architecture-diagrams.md
  - implementation-constraints.md
  - verification-scenarios.md
sources:
  - ../../planning-artifacts/prds/prd-Desafio tecnico Artefact-2026-11-02/prd.md
  - ../../planning-artifacts/prds/prd-Desafio tecnico Artefact-2026-11-02/addendum.md
  - ../../planning-artifacts/architecture/architecture-Desafio tecnico Artefact-2026-11-02/ARCHITECTURE-SPINE.md
  - ../../planning-artifacts/architecture/architecture-Desafio tecnico Artefact-2026-11-02/reconcile-inputs.md
---

# Empório da Música Trusted AI Assistant

## Why

Empório da Música needs a trustworthy conversational assistant for catalog, price, availability, policy, and authorized order questions. The Artefact challenge makes this a prototype mandate: demonstrate useful natural-language interaction without inventing operational facts, leaking customer data, or requiring external credentials for the core path.

## Capabilities

- **CAP-1**
  - **intent:** A Customer can ask for store information and policy guidance in Brazilian Portuguese.
  - **success:** Answers use the Policy Source, distinguish policy types, expose relevant provenance, and state when evidence is insufficient or contradictory.

- **CAP-2**
  - **intent:** A Customer can search available Products and request exact Product details.
  - **success:** Available results are active and in stock, bounded and ordered; prices come from the Operational Snapshot and missing Products are not invented.

- **CAP-3**
  - **intent:** A Customer can ask for Promotion, PIX, installment, and shipping outcomes for a Product or amount.
  - **success:** Deterministic rules use decimal currency arithmetic, do not stack incompatible discounts, and handle documented boundaries explicitly.

- **CAP-4**
  - **intent:** An authorized Customer can check the status of an Order.
  - **success:** Only a server-established Authorized Principal can receive owned Order details; anonymous, cross-customer, invalid, and nonexistent requests do not disclose private data.

- **CAP-5**
  - **intent:** A Customer can continue a question within an isolated Session.
  - **success:** Follow-ups retain relevant context, sessions do not share identity or history, and expiry/storage failure cannot restore stale private context.

- **CAP-6**
  - **intent:** The Assistant can use safe Tools to answer requests and recover from unavailable data or providers.
  - **success:** Only allowlisted, schema-validated Tools execute with authorization, timeouts, and a hard round budget; failures produce honest responses.

- **CAP-7**
  - **intent:** An evaluator can run and test the P0 Assistant locally without external credentials.
  - **success:** FakeLLM, SQLite, deterministic fixtures, and automated tests cover the core path offline.

- **CAP-8**
  - **intent:** A Developer can change the LLM provider without changing domain behavior.
  - **success:** Providers conform to one normalized boundary, capabilities are checked before execution, and provider contract tests pass.

- **CAP-9**
  - **intent:** An evaluator can verify safety, provenance, limitations, and failure behavior.
  - **success:** Automated scenarios cover privacy, prompt injection, unavailable tools, ambiguous policies, unsupported actions, snapshot freshness, and provider failure.

- **CAP-10**
  - **intent:** Optional channel and integration adapters can reuse the P0 use cases.
  - **success:** WhatsApp, market comparison, and MCP remain independently configurable and cannot change official Product facts or block offline P0 behavior.

## Constraints

- Exact operational facts come from the supplied CSV Operational Snapshot; policy answers come from the Policy Source with provenance.
- Order access requires a server-established Authorized Principal; chat text, identifiers, and contact data cannot authenticate a Customer.
- P0 must run without network credentials, and raw customer PII must not appear in logs or public fixtures by default.
- Business rules remain deterministic and outside the language model.
- The implementation follows the finalized Hexagonal Architecture spine, including dependency direction, single state ownership, safe Tool execution, and sanitized observability.
- Customer-facing responses use Brazilian Portuguese and disclose uncertainty, data freshness, and unavailable capabilities.

## Non-goals

- Checkout, payment capture, cancellation, refunds, ticket creation, or real human escalation.
- Live ERP inventory, live delivery tracking, or production customer authentication.
- Mandatory WhatsApp, market search, MCP, cloud deployment, vector database, or multi-agent runtime.
- Public release of raw customer PII or unapproved internal source documents.
- A claim that every LLM provider supports every capability.

## Success signal

An evaluator can run the local Assistant, ask catalog, policy, PIX, and order questions, and observe correct grounded answers plus safe refusals for unauthorized, unsupported, injected, and unavailable cases. The P0 suite passes offline, with at least three executed demonstrations and no unauthorized private-data disclosure.

## Assumptions

- The workspace root remains the implementation root until bootstrap confirms otherwise.
- A clearly labeled simulated Authorized Principal is acceptable for local demonstrations.
- Raw customer and internal policy sources remain private until publication permission is confirmed; anonymized fixtures may be created.

## Open Questions

- Which implementation root and first delivery surface are selected before bootstrap?
- Which exact interpretation applies to the R$500 shipping boundary and installment minimums?
- Which real LLM provider and model are available for the optional provider demonstration?
- What snapshot date and policy retrieval threshold are used in acceptance tests?
