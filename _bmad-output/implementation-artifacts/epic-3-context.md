# Epic 3 Context: Run and Extend the Trusted Assistant

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Enable evaluators and developers to run the assistant reproducibly without external credentials, verify its safety and behavior, switch language-model providers through a stable contract, and add optional channels or integrations without changing trusted P0 business rules. The core path must remain available when optional providers or integrations are absent or fail.

## Stories

- Story 3.1: Run and Verify the Assistant Offline
- Story 3.2: Add Optional External Integrations

## Requirements & Constraints

- The P0 suite must run offline with SQLite, deterministic/anonymized fixtures, and `FakeLLM`; external credentials and network access must not be required.
- Verification must cover catalog and policy behavior, payment, order authorization, prompt injection, provider/tool failures, unsupported actions, ambiguity, and partial results. The suite must have zero unauthorized private-data disclosures.
- Setup and test commands must be documented and reproducible in a clean supported environment. Executed demonstrations should make snapshot dates, assumptions, limitations, and provenance visible.
- Provider selection must be explicit and configuration-driven. A missing or incompatible provider configuration must fail clearly while leaving FakeLLM mode usable.
- Customer-facing answers must use clear Brazilian Portuguese and communicate uncertainty, unavailable data, incomplete results, and snapshot freshness rather than inventing values.
- Observability must provide structured correlation, provider/tool outcome, duration, success, and error information while excluding raw prompts, sensitive message text, and customer PII by default.
- Optional integrations must be feature-flagged and isolated. Their credentials, outages, or implementation status must never block the offline P0 path.
- WhatsApp webhook inputs require validation, signature verification when configured, normalization, and idempotent duplicate-message handling. Real Meta delivery must not be claimed without verified credentials and an integration test; secrets belong in documented environment variables.
- Market comparison may return only provenance-bearing offers for exact product matches. Offers must remain separate from official product price data; variant mismatches and insufficient independent offers must be rejected or labeled.
- MCP may expose selected supported use cases, but it is not required for the local assistant and must preserve existing authorization and domain behavior.

## Technical Decisions

- Use hexagonal architecture with inward dependency direction. Domain and application code must not import provider SDKs, web frameworks, Meta APIs, MCP libraries, or database libraries.
- Normalize language-model interactions behind `LLMPort` and `LLMFactory`, including messages, tool calls, results, usage, and capabilities. Validate required capabilities before execution; provider SDK types remain in adapters.
- Keep all channels on the shared `InboundMessage`/`OutboundMessage` contracts and `ConversationService`. Adapters handle transport concerns only and do not duplicate catalog, policy, payment, or authorization rules.
- Implement optional WhatsApp, market, and MCP capabilities as ports/adapters. Market observations have their own ownership boundary and must never overwrite official Product data.
- Use explicit configuration allowlists for providers and optional adapters. User input must never select an import path, executable, or arbitrary integration.
- Keep the existing allowlisted, schema-validated, authorized, timeout-bounded tool boundary and typed safe-error mapping. Do not expose stack traces, provider payloads, SQL, or private existence details.
- Use contract tests at each port boundary, deterministic unit tests for domain rules, integration tests for adapters, and scenario/security tests for the conversation path.
- Preserve provenance: external offers include retailer/source, URL, observation date, condition, and match information; structured facts retain snapshot context.

## UX & Interaction Patterns

- Local CLI/HTTP remain the primary validation surfaces; WhatsApp is an optional remote channel over the same conversation service.
- Integration status must be transparent: distinguish configured, mocked, unavailable, incomplete, and snapshot-based behavior. Failures should produce concise, honest Brazilian Portuguese responses and preserve core assistance.
- Responses and demonstrations should expose appropriate source provenance and freshness context without leaking private data.

## Cross-Story Dependencies

- Story 3.1 establishes the reproducible runtime, normalized provider boundary, observability, test harness, fixtures, and shared conversation contracts required by Story 3.2.
- Story 3.2 depends on the P0 domain use cases and authorization rules from Epics 1 and 2; optional adapters must reuse them rather than implement parallel business logic.
- Story 3.2 is intentionally post-P0/optional. Failures or missing credentials in WhatsApp, market comparison, or MCP must not reduce the availability of Story 3.1 or core catalog, policy, payment, session, and authorized-order behavior.
