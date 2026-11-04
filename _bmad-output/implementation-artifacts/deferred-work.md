# Deferred Work

- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-answer-store-and-policy-questions.md`
  summary: Evaluate whether lexical retrieval should require stronger evidence than one shared term.
  evidence: A generic one-term query can match a passage, but the approved intent does not define a multi-term threshold; representative query evaluation is needed before changing retrieval semantics.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-answer-store-and-policy-questions.md`
  summary: Add section-level segmentation for PDF pages containing multiple numbered sections.
  evidence: The adapter currently assigns the first detected section to a page; the supplied source shape and a failing provenance example were not established.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-answer-store-and-policy-questions.md`
  summary: Improve extraction handling for embedded PDF font encodings.
  evidence: The local challenge PDF yields mojibake from the extraction library; the issue is source encoding-specific and needs a parser or source replacement decision.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-answer-store-and-policy-questions.md`
  summary: Expand injection sanitization and add inline-instruction fixtures.
  evidence: Review identified untested inline and Portuguese variants, but no reachable behavior change was demonstrated beyond the covered line-oriented fixture.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-answer-store-and-policy-questions.md`
  summary: Evaluate retrieval and ambiguity behavior beyond the bounded top-five result set.
  evidence: Conflicts beyond five passages and alternate phone formats were not demonstrated in the supplied policy source or acceptance examples.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-answer-store-and-policy-questions.md`
  summary: Add query-specific CLI messaging for invalid questions.
  evidence: The safe CLI error path currently uses source-failure wording for all PolicyError values; the story requires safe handling but does not prescribe distinct copy.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-search-products-and-show-exact-availability.md`
  summary: Make catalog reads use one explicit transaction when capturing rows and snapshot metadata.
  evidence: Concurrent snapshot replacement could theoretically combine a page read with metadata from a different snapshot; reproduce under concurrent ingestion before changing the repository contract.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-search-products-and-show-exact-availability.md`
  summary: Evaluate Unicode-aware case-insensitive catalog matching.
  evidence: SQLite LOWER() behavior for accented Portuguese variants may differ from customer expectations; settle with a supported-runtime query matrix before adding normalization infrastructure.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-3-apply-promotions-and-calculate-payment-options.md`
  summary: Add a transaction-scoped repository read for product and promotion payment calculations.
  evidence: PaymentService currently reads the product and active promotions through separate repository calls; reproduce a concurrent snapshot replacement before changing the repository API.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-1-check-authorized-order-status.md`
  summary: Introduce immutable version IDs and a transaction-scoped read spanning order, items, and snapshot metadata.
  evidence: P0 rejects mixed catalog/order refreshes and keeps the read path bounded, but a concurrent replacement can still require a stronger versioned snapshot contract before production use.
- source_spec: `_bmad-output/implementation-artifacts/spec-3-2-add-optional-external-integrations.md`
  summary: Certify live Correios and Meta credentials/endpoints in an integration environment and expose production transports.
  evidence: Offline fake-provider contracts and secure configuration are implemented; real credentials and provider certification were intentionally not required for P0.
- source_spec: `_bmad-output/implementation-artifacts/spec-dev-order-tracking.md`
  summary: Distinguish minimum-price requests from maximum budgets and validate catalog argument types before rewriting.
  evidence: Pre-existing grounded_search_arguments treats monetary amounts as ceilings and applies regex before the tool schema validates numeric names.
- source_spec: `_bmad-output/implementation-artifacts/spec-dev-order-tracking.md`
  summary: Derive delivery corrections from retrieved evidence and generalize destination detection.
  evidence: The pre-existing delivery guard contains fixed deadlines and São Paulo wording, and rejects the outside-Campo-Grande phrase at its early return.
- source_spec: `_bmad-output/implementation-artifacts/spec-dev-order-tracking.md`
  summary: Retain sufficient policy passages for combined customer questions.
  evidence: The earlier store/payment/return retrieval branch keeps one passage regardless of how many policy topics were asked.
- source_spec: `_bmad-output/implementation-artifacts/spec-dev-order-tracking.md`
  summary: Respect explicit provider tool-disable configuration and restore bounded catalog limit compatibility.
  evidence: Earlier runtime work lets model detection override the false flag and removed limit from the search_catalog tool schema; neither behavior was introduced by simulated orders.
- source_spec: `_bmad-output/implementation-artifacts/spec-dev-order-tracking.md`
  summary: Normalize specific installment results and validate installment count/amount pairs.
  evidence: Existing quote validation only recognizes overview results with maximum_installments and independently checks amounts and counts, permitting mispaired plans.
- source_spec: `_bmad-output/implementation-artifacts/spec-dev-order-tracking.md`
  summary: Preserve selected product context for payment follow-ups without model codes.
  evidence: Existing follow-up handling can trim the history without putting the resolved product name into the model context when the name contains no recognized code.
- source_spec: `_bmad-output/implementation-artifacts/spec-dev-order-tracking.md`
  summary: Persist pending messages when SessionService recovers into a replacement session.
  evidence: Existing append failure recovery creates a new session and returns the triggering user message in memory; a later successful assistant append can reload persisted history without it. Simulation session rebinding is fixed separately.
- source_spec: `_bmad-output/implementation-artifacts/spec-dev-order-tracking.md`
  summary: Teach the local diagnostic capture mode to execute orchestrated payment plans.
  evidence: The earlier diagnostic expects its capture delegate to run on the first round, while mandatory payment planning can return a tool call first.
- source_spec: `_bmad-output/implementation-artifacts/spec-dev-order-tracking.md`
  summary: Optionally paginate simulated order history beyond thirty recent entries.
  evidence: The local test panel deliberately bounds recent orders at thirty; older records remain stored and can be queried by owned reference, but adding UI pagination would expose their lifecycle controls.
