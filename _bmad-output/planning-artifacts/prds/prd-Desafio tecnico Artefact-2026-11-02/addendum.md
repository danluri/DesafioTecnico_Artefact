# PRD Addendum — Empório da Música Trusted AI Assistant

This addendum preserves technical depth from the source documents without making implementation choices part of the product contract.

## Source reconciliation

The source package is internally consistent on the main product thesis: structured data must answer exact operational questions, policy answers must be retrieved with provenance, and private order data must be authorization-gated. The existing documents are proposals for BMAD refinement rather than evidence of completed implementation.

The package includes:

- `PROJECT_BRIEF.md`: problem, priorities, constraints, and delivery expectations.
- `PRD.md`: existing functional requirements and policy ambiguities.
- `ARCHITECTURE.md`: Ports & Adapters design, LLM Factory, tool loop, retrieval, channels, and optional integrations.
- `DATA_MODEL.md`: source inventory, relationships, anomalies, and proposed application tables.
- `ROADMAP.md`: milestone and story sequence.
- `TEST_STRATEGY.md`: deterministic, contract, integration, API, evaluation, and security tests.
- `BMAD_HANDOFF.md`: intended refinement and execution workflow.

## Technical decisions retained for downstream architecture

1. Use a normalized `LLMPort` and provider adapters; keep SDKs out of domain and orchestration code.
2. Keep deterministic domain services for catalog, promotion, payment, shipping, availability, and order ownership.
3. Use structured SQL-style retrieval for operational data and section-aware textual retrieval for the policy document.
4. Treat CLI/API as the P0 channel; WhatsApp is an optional adapter over the same conversation service.
5. Keep Market Comparison and MCP as optional adapters with feature flags, provenance, mocks, and no duplicated business rules.
6. Use a fake LLM and local fixtures to make the basic test suite independent of network credentials.
7. Keep Ponytail outside runtime, package dependencies, and CI requirements.

## Rejected or deferred alternatives

- A single LLM over the entire corpus was rejected because it weakens exact-value correctness, provenance, and access control.
- A vector database for all data was deferred because structured queries are a better baseline for exact operational facts and the policy corpus is small.
- A universal provider abstraction promising identical support for every model was rejected; capabilities must be verified and surfaced.
- Real WhatsApp, web market search, and MCP are deferred until P0 is stable because credentials, external failure, and security controls add delivery risk.
- Copying a third-party `AGENTS.md` over project instructions is rejected; project-specific security and scope rules take precedence.

## Downstream implementation guardrails

- Import validation must be atomic and idempotent; invalid types, foreign keys, JSON, or statuses must not leave a partial database.
- Monetary values use `Decimal` and a documented BRL rounding rule.
- Logs use correlation IDs and tool outcomes without raw customer PII or sensitive message text by default.
- Tool schemas are allowlisted and validated before execution; authorization is enforced by the server-side use case, not by the prompt.
- Retrieval chunks carry section, page, source file, and document version metadata.
- Tests must include unavailable data, inactive/zero-stock products, discontinued products with positive stock, unauthorized orders, prompt injection, provider failure, and ambiguous policy questions.

## Recommended P0 delivery sequence

1. Establish the implementation root, Python package, dependency policy, lint/type/test commands, and anonymized fixtures.
2. Implement ingestion and deterministic domain services.
3. Implement policy extraction, indexing, retrieval, and source provenance.
4. Implement fake LLM contracts, one real adapter if available, and bounded tool orchestration.
5. Add session continuity and one local interface.
6. Execute the security and behavior matrix, then produce README and conversation evidence.
7. Only after the P0 gate, consider WhatsApp, market comparison, or MCP.
