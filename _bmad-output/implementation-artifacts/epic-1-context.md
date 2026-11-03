# Epic 1 Context: Discover Products and Understand Store Policies

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Enable customers to obtain trustworthy store guidance, search the available product catalog, see snapshot-based prices and promotions, and calculate payment or shipping options. Answers must use the appropriate authoritative source, expose uncertainty and freshness where relevant, and never invent products, prices, policies, contact details, or commercial rules.

## Stories

- Story 1.1: Answer Store and Policy Questions
- Story 1.2: Search Products and Show Exact Availability
- Story 1.3: Apply Promotions and Calculate Payment Options

## Requirements & Constraints

- Store and policy answers must be concise, informal-professional Brazilian Portuguese. Cover store address, opening hours, product scope, contact channels, payment, shipping, returns, exchanges, and warranty.
- Policy answers must come from relevant, section-aware Policy Source content and include provenance when appropriate. Distinguish online regret, store exchange, and legal warranty. If content is missing or contradictory, ask for context or recommend confirmation; do not fill gaps from general model knowledge.
- Conflicting documented contact details must be reported as a discrepancy, not silently resolved.
- Product searches may use natural-language category, name, and budget criteria. Availability results include only active products with positive stock, and results are deterministic, bounded, ordered, and paginated.
- Exact product details and prices must come from the Operational Snapshot, be formatted in BRL, and be identified as snapshot-based when freshness matters. No-match, ambiguous, invalid, or poor-quality records must produce safe clarification/not-found behavior rather than fabricated values.
- Promotions must use active snapshot records only. Responses separate original price, discount, and promotional price; multiple active promotions require explicit handling and must never be silently summed.
- PIX, installment, and shipping calculations are deterministic. Use BRL-safe decimal arithmetic and the declared rounding rule. Apply the documented PIX discount only when no promotion applies; do not stack discounts. Communicate documented assumptions for ambiguous boundaries such as shipping at exactly R$500 or installment minimums.
- Success is demonstrated by deterministic catalog, promotion, payment, shipping, and policy-retrieval tests, including missing-data, ambiguity, contradiction, boundary, and prompt-injection cases.

## Technical Decisions

- Use Hexagonal Architecture with inward dependency direction. Domain/application services own product price, availability, promotion, payment, shipping, and provenance rules; the LLM cannot author returned facts.
- Keep structured operational retrieval separate from policy retrieval. Use typed repositories and parameterized queries for catalog facts; use a `PolicyRetrieverPort` for bounded passages with source file, document version, section, and page metadata.
- Use SQLite as the P0 persistence boundary for the operational snapshot and policy chunks/index. Ingestion is validated and atomic; invalid source records are rejected rather than silently normalized. Preserve source IDs.
- Expose capabilities through an allowlisted, schema-validated `ToolRegistry`; apply server-side authorization, timeout, and call-budget controls. Do not permit arbitrary SQL, shell commands, dynamic imports, or unknown tools.
- Use `Decimal` for all customer-visible money calculations and explicit domain rounding rules. Expose a configured or derived `data_as_of`; snapshot data is not live inventory or live pricing.
- Keep provider/framework dependencies outside domain and application code. `LLMPort`/`LLMFactory` normalize providers, and `FakeLLM` remains available for offline deterministic tests.
- Use typed internal errors and safe responses; do not expose SQL, stack traces, provider payloads, or untrusted document instructions.

## UX & Interaction Patterns

Customer-facing responses are clear, concise Brazilian Portuguese with transparent uncertainty. Follow-up questions may refer to the product or policy context already established in the current session. Summarize only the policy content needed for the question rather than exposing the complete internal document. When a result is snapshot-based, stale-sensitive, ambiguous, unavailable, or incomplete, state that plainly and ask only for the context needed to continue.

## Cross-Story Dependencies

- Story 1.1 depends on policy ingestion and section-aware retrieval with reliable provenance; it must not fall back to catalog retrieval for policy prose.
- Story 1.2 depends on validated operational-snapshot ingestion and typed product queries, including active-status and stock filtering.
- Story 1.3 depends on Story 1.2’s product/promotion data and on documented policy rules for PIX, installments, and shipping. Promotion application must precede payment calculation so discounts cannot be stacked.
- All three stories share the ConversationService and allowlisted tool boundary, while remaining independent of optional WhatsApp, market-comparison, and MCP integrations.
