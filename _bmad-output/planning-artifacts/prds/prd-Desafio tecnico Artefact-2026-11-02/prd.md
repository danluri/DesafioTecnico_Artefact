---
title: Empório da Música Trusted AI Assistant
status: final
created: 2026-11-02
updated: 2026-11-02
---

# PRD: Empório da Música Trusted AI Assistant

## 0. Document Purpose

This PRD defines the product behavior and acceptance criteria for the Empório da Música AI assistant, a Python prototype prepared for the Artefact AI Engineer challenge. It is intended for downstream UX, architecture, story-planning, implementation, and review work. It reconciles the existing `PROJECT_BRIEF.md`, `PRD.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`, `ROADMAP.md`, `TEST_STRATEGY.md`, and `BMAD_HANDOFF.md`. Technical mechanisms and rejected alternatives are kept in the companion `addendum.md`.

The product is a prototype, not a production commerce platform. Information derived from the supplied CSV files is a dated snapshot, and information derived from the internal policy document must remain traceable to its source.

## 1. Vision

Empório da Música customers should be able to ask natural-language questions about musical instruments, prices, availability, store information, commercial policies, and their own orders without receiving invented facts. The assistant earns trust by using the appropriate source for each question: structured operational data for exact values and a traceable policy source for textual rules.

The central product bet is that a smaller, explicit, testable assistant is more useful for this challenge than a broad autonomous agent. Deterministic business rules, authorization, source provenance, and honest limitations take precedence over conversational breadth or optional integrations.

The prototype must be easy for an evaluator to run locally, inspect, and test without external credentials. A real LLM provider and optional channels may demonstrate extensibility, but the core product must remain reproducible offline.

## 2. Target User

### 2.1 Jobs To Be Done

- A customer wants to find a suitable available instrument within a budget.
- A customer wants an exact product price, promotion, PIX amount, or installment option.
- A customer wants to understand a store policy in plain Portuguese.
- A customer wants to check an order without exposing another customer's information.
- A customer wants a follow-up question to retain the context of the current conversation.
- An evaluator wants to verify that answers are grounded, safe, reproducible, and honest about snapshot data.
- A developer wants to change the language-model provider without changing business behavior.

### 2.2 Non-Users (v1)

- Staff operating a full ERP or warehouse-management system.
- Customers completing checkout, cancellation, refunds, or support tickets inside the assistant.
- Anonymous users receiving private order details.
- Users expecting live inventory, live delivery tracking, or guaranteed current competitor prices.

### 2.3 Key User Journeys

- **UJ-1. Ana finds a playable instrument within her budget.** Ana asks for available violões up to R$1,000. The assistant searches the operational snapshot, excludes inactive or out-of-stock products, returns exact prices, and says that availability reflects the dataset snapshot rather than a live ERP. Ana asks a follow-up about PIX and receives a calculation for the product already identified.

- **UJ-2. Bruno checks a policy before returning an online purchase.** Bruno asks whether an item received yesterday can be returned. The assistant retrieves the relevant policy section, distinguishes online regret from exchange and legal warranty, cites the source section or page, and asks for missing context when the policy depends on purchase channel or timing.

- **UJ-3. Carla checks her order without crossing an authorization boundary.** Carla asks for order status. The server provides an authorized principal for the demo session; only an order belonging to that principal is disclosed. If no authorized principal exists, or the order belongs to another customer, the assistant refuses the private details and explains the safe next step.

- **UJ-4. Diego evaluates the prototype.** Diego starts the local application without external credentials, runs deterministic tests, and exercises catalog, policy, authorization, failure, and out-of-scope scenarios. The README and executed conversation transcripts make the snapshot date, assumptions, limitations, and AI tooling visible.

## 3. Glossary

- **Assistant** — The Empório da Música conversational product described by this PRD.
- **Customer** — A person asking the Assistant for store or order information.
- **Operational Snapshot** — The supplied CSV dataset imported for this prototype; it is not live inventory or live order tracking.
- **Policy Source** — The supplied store-policy document, segmented into traceable sections and pages.
- **Product** — A musical instrument or other catalog item represented in the Operational Snapshot.
- **Promotion** — A snapshot record describing an active or inactive discount associated with a Product.
- **Order** — A customer purchase represented in the Operational Snapshot.
- **Authorized Principal** — A server-established identity allowed to access a specific Customer's private Order data.
- **Session** — An isolated conversation context containing bounded history and, when applicable, an Authorized Principal.
- **Source Provenance** — The source identifier, snapshot/document version, and retrieval time needed to explain where a response came from.
- **Tool** — An allowlisted product capability used by the Assistant to query data or retrieve policy content.
- **External Offer** — A third-party market observation, kept separate from the official Product price.

## 4. Features

### 4.1 Store Information and Policy Answers

**Description:** The Assistant answers store-information and commercial-policy questions in Brazilian Portuguese using the Policy Source. It should distinguish a known policy from an unresolved ambiguity, avoid exposing the complete internal document, and identify the relevant source section or page when practical. This realizes UJ-2 and UJ-4.

#### FR-1: Store information

Customers can ask about address, opening hours, contact channels, and the store's product scope.

**Consequences (testable):**

- The Assistant returns the documented address and hours: Monday–Friday 09:00–18:00 and Saturday 09:00–13:00; Sunday and holidays are closed.
- It does not invent exceptional hours, current staffing, or a live contact state.
- Conflicting contact details are communicated as an unresolved documented discrepancy rather than silently presented as certain.

#### FR-2: Policy retrieval

Customers can ask about payment, shipping, returns, exchanges, and warranty policies.

**Consequences (testable):**

- The response is based on one or more retrieved Policy Source sections with source provenance.
- The response distinguishes online regret, store exchange, and legal warranty.
- If the retrieved content is insufficient or contradictory, the Assistant asks for relevant context or recommends human confirmation instead of guessing.
- If no passage meets the retrieval evidence threshold, the Assistant states that the policy answer is unavailable rather than filling the gap from general model knowledge.
- Missing source version or page metadata prevents the response from being presented as fully traceable.

#### FR-3: Payment and shipping calculation

Customers can ask for PIX, installments, and local shipping conditions for a Product or purchase amount.

**Consequences (testable):**

- PIX applies the documented 5% rule only when the Product is not covered by a Promotion; discounts are not stacked.
- Credit installments respect the documented installment bands and minimum-value rule used by the implementation.
- Currency calculations use BRL-safe decimal arithmetic and a declared rounding rule.
- The exact R$500 shipping boundary is handled by an explicit documented assumption until confirmed.

### 4.2 Catalog, Price, Availability, and Promotion

**Description:** The Assistant uses structured Operational Snapshot data for exact catalog facts. It never treats the language model as the source of truth for Product price, stock, or Promotion state. This realizes UJ-1 and UJ-4.

#### FR-4: Product search

Customers can search Products by natural-language criteria such as category, name, and maximum budget.

**Consequences (testable):**

- Search results include only Products with `status=active` and positive stock when the user asks what is available.
- Results are deterministic, bounded, ordered, and paginated.
- No result is fabricated when the dataset contains no matching Product.
- Empty, malformed, contradictory, or ambiguous filters produce validation or clarification rather than an arbitrary query.
- Invalid page size or pagination state is rejected or clamped to a documented safe limit.

#### FR-5: Product details and price

Customers can request details and price for a named Product.

**Consequences (testable):**

- The displayed price comes from the Operational Snapshot and is formatted in BRL.
- The response identifies the data as a snapshot when freshness could matter.
- A missing or ambiguous Product produces clarification or an honest not-found response.
- A Product with invalid monetary or stock data is excluded from customer answers and reported as an ingestion-quality issue.

#### FR-6: Promotion handling

Customers can ask whether a Product has a Promotion.

**Consequences (testable):**

- Only the snapshot's active Promotion record is applied.
- The response separates original price, discount percentage, and promotional price.
- Multiple active Promotions are detected and handled by an explicit policy; percentages are never silently summed.
- A seasonal statement in the Policy Source is not treated as proof of a currently active Promotion.

### 4.3 Authorized Order Status

**Description:** The Assistant provides limited order information only when the server supplies an Authorized Principal. A phone number, name, e-mail, or order ID typed into the conversation is not authentication by itself. This realizes UJ-3.

#### FR-7: Order authorization

The system can verify that an Order belongs to the Authorized Principal before returning private details.

**Consequences (testable):**

- An anonymous request cannot retrieve order status, customer data, items, or tracking details.
- An Authorized Principal can retrieve only an Order belonging to its customer identity.
- A principal belonging to another Customer receives a denial without an existence-enumeration leak.
- Invalid, malformed, or nonexistent Order identifiers use the same non-enumerating safe response as unauthorized access.
- A demo principal is explicitly labeled as simulated and is never represented as production authentication.

#### FR-8: Snapshot order status

An authorized Customer can ask for the status of an Order.

**Consequences (testable):**

- The response is based on the Operational Snapshot and does not promise live tracking.
- Only the minimum necessary order details are disclosed.
- Missing tracking information is reported as unavailable rather than invented.

### 4.4 Conversational Continuity and Safe Boundaries

**Description:** The Assistant supports multi-turn questions within an isolated Session, while maintaining bounded context, tool limits, and safe fallback behavior. This realizes UJ-1, UJ-2, UJ-3, and UJ-4.

#### FR-9: Session context

Customers can ask a follow-up question that refers to a Product, policy topic, or prior clarification in the same Session.

**Consequences (testable):**

- A follow-up such as “And by PIX?” retains the relevant Product context.
- Sessions do not share history or Authorized Principal state.
- Context is bounded and does not cause unbounded storage or prompt growth.
- Session expiration or storage failure creates a fresh isolated context and never restores stale private context implicitly.

#### FR-10: Tool-mediated answers

The Assistant can select only allowlisted Tools with validated arguments.

**Consequences (testable):**

- The language model cannot execute arbitrary SQL, shell commands, dynamic imports, or unknown Tools.
- Tool arguments are schema-validated and authorization is checked server-side.
- Tool calls have a timeout and maximum-round budget.
- Tool failures return a safe, honest response without fabricated data.
- Partial or incomplete Tool results are labeled incomplete; missing fields are not filled by inference.
- A selected provider without required credentials or capabilities fails with an actionable configuration response and leaves fake mode available.

#### FR-11: Scope and limitation handling

The Assistant can refuse or redirect requests outside the store's supported scope.

**Consequences (testable):**

- Requests about unrelated product categories do not produce invented catalog results.
- Missing data, unavailable external integrations, and unsupported actions are stated plainly.
- The Assistant does not claim to have completed checkout, cancellation, refunds, tickets, or human escalation unless that action actually exists.

### 4.5 Optional Extensions After P0

**Description:** Optional extensions may reuse the same Assistant capabilities without changing core business rules. They must not delay the P0 path and must be clearly labeled when only mocked or partially configured.

#### FR-12: WhatsApp channel adapter `[NON-GOAL for MVP]`

The system may accept and send normalized messages through a WhatsApp adapter.

**Consequences (testable):**

- Webhook payloads are validated, signatures are checked when configured, and duplicate external message IDs are idempotent.
- Real Meta delivery is not claimed without verified credentials and an executed integration test.

#### FR-13: Market comparison `[NON-GOAL for MVP]`

The system may show External Offers for an exact Product match.

**Consequences (testable):**

- External Offers remain separate from the official Product price and include source, link, date, and match information.
- Variant mismatches and insufficient independent offers are rejected or clearly labeled.
- External-provider failure does not block catalog or policy assistance.
- Duplicate observations from the same retailer do not count as independent offers for market aggregation.

#### FR-14: MCP adapter `[NON-GOAL for MVP]`

The system may expose selected capabilities through an MCP adapter.

**Consequences (testable):**

- MCP calls reuse the same domain services and authorization checks.
- MCP is not required for the local Assistant to function.

## 5. Cross-Cutting Non-Functional Requirements

### Security and privacy

- No customer PII is written to logs by default.
- Customer and Order data are minimized and access-controlled.
- Prompt injection and untrusted external text are treated as data, not privileged instructions.
- SQL is parameterized; the language model cannot issue arbitrary queries.

### Reliability and honesty

- Core P0 behavior runs with a fake language model and local data, without network credentials.
- Every dynamic answer carries or can expose Source Provenance appropriate to the surface.
- Timeouts, tool budgets, provider failures, missing data, and ambiguous policies have explicit fallback behavior.

### Reproducibility and quality

- A fresh evaluator can install documented dependencies, run the application, and execute the automated tests.
- Tests cover success, failure, boundary, authorization, privacy, and prompt-injection cases.
- The final README records commands actually run, assumptions, limitations, AI-tool usage, and three to five executed conversation transcripts.

### Language and tone

- Customer-facing responses are in Brazilian Portuguese, informal-professional, concise, and transparent about uncertainty.
- Internal policy content is summarized only to answer the question; the complete document is not exposed by default.

## 6. Constraints and Guardrails

- The CSV files are an Operational Snapshot, not live ERP data.
- The supplied policy document may contain contradictory contact information and ambiguous commercial wording.
- Invalid source records are rejected during ingestion rather than normalized silently into customer-visible facts.
- Public-repository publication of `customers.csv` and internal policy content requires an explicit permission and privacy decision.
- The prototype must not imply production authentication, live tracking, live stock, or guaranteed current market pricing.
- Ponytail, BMAD, Codex, and other development tools are process aids, not runtime dependencies.

## 7. Non-Goals (Explicit)

- Checkout, payment capture, cancellation, refund execution, or ticket creation.
- Real ERP synchronization or live inventory reservation.
- Production-grade customer authentication and identity recovery.
- Guaranteed live delivery tracking.
- Mandatory WhatsApp, market search, MCP, cloud deployment, vector database, or multi-agent runtime.
- A claim that every LLM provider supports every capability.

## 8. MVP Scope

### 8.1 In Scope

- Local CLI and/or HTTP surface for the Assistant.
- CSV ingestion and validated structured queries for Products, Promotions, Categories, Customers, Orders, and order items.
- Policy extraction/retrieval with section and page provenance.
- Deterministic Product, Promotion, payment, shipping, and authorization behavior.
- Session continuity and bounded tool-mediated orchestration.
- Fake LLM plus at least one demonstrated real-provider adapter, when credentials are available.
- Automated tests, security-negative tests, README, and executed demonstrations.

### 8.2 Out of Scope for MVP

- Real WhatsApp delivery, market search, and MCP exposure; these remain optional post-MVP increments.
- Any feature requiring external credentials for the basic test suite.
- Public release of raw customer PII or unapproved internal source documents.

## 9. Success Metrics

These are acceptance targets for the prototype, not production SLAs.

### Primary

- **SM-1:** 100% of deterministic catalog, price, promotion, payment, and authorization tests return the expected result. Validates FR-3 through FR-8.
- **SM-2:** 0 unauthorized private-data disclosures across the negative authorization and prompt-injection suite. Validates FR-7, FR-10, and FR-11.
- **SM-3:** 100% of core offline tests pass without network credentials. Validates FR-4 through FR-11 and reproducibility.
- **SM-4:** At least three executed conversation demonstrations cover catalog/PIX, policy, and order authorization. Validates UJ-1 through UJ-4.

### Secondary

- **SM-5:** The policy retrieval evaluation recovers the expected source section for the documented test questions at the agreed top-k threshold. Validates FR-2.
- **SM-6:** A provider swap changes configuration rather than domain behavior or tool contracts. Validates extensibility under FR-10.

### Counter-metrics

- **SM-C1:** Number of optional integrations shipped. This must not be optimized at the expense of P0 correctness, privacy, or reproducibility.
- **SM-C2:** Lines of code or token/tool-call reduction. Shorter code is not success if it weakens authorization, provenance, or tests.

## 10. Open Questions

1. Should the project use the workspace root as the implementation repository, or should the architecture package become the repository root?
2. Is publication of the supplied customer CSV and internal policy PDF authorized? If not, which anonymized fixtures and policy extracts may be committed?
3. What is the authoritative interpretation of shipping for an order exactly at R$500?
4. What is the authoritative minimum installment amount for the 1–3 installment band?
5. Which contact phone and e-mail should the product present while the source discrepancy remains unresolved?
6. Which real LLM provider is available for the one-provider demonstration, if any?
7. What date should be used as the Operational Snapshot's explicit `data_as_of` value?
8. What retrieval evidence threshold and top-k value will be used for the first policy evaluation suite?

## 11. Assumptions Index

- **[ASSUMPTION: prototype form factor]** The MVP will expose at least one local CLI or HTTP surface; both are desirable only if they do not threaten P0 delivery.
- **[ASSUMPTION: implementation root]** The BMAD workspace root will remain the working repository while the existing architecture package is reconciled into it.
- **[ASSUMPTION: demo authorization]** A server-injected simulated Authorized Principal is acceptable for local demonstrations, explicitly labeled as non-production.
- **[ASSUMPTION: provider availability]** The fake LLM is mandatory for offline tests; a real provider is demonstrated only when credentials and budget are available.
- **[ASSUMPTION: source publication]** Raw customer PII and internal source documents will not be published until permission is confirmed; anonymized fixtures may be created.
- **[ASSUMPTION: snapshot date]** The implementation will expose a configured or derived `data_as_of` value rather than describing the data as current.
- **[ASSUMPTION: unresolved commercial rules]** Shipping at exactly R$500, installment minimums, and conflicting contacts remain explicit product assumptions until confirmed.
