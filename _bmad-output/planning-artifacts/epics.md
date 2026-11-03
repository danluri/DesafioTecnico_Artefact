---
status: final
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - _bmad-output/specs/spec-Desafio tecnico Artefact/SPEC.md
  - _bmad-output/specs/spec-Desafio tecnico Artefact/capabilities.md
  - _bmad-output/planning-artifacts/prds/prd-Desafio tecnico Artefact-2026-11-02/prd.md
  - _bmad-output/planning-artifacts/architecture/architecture-Desafio tecnico Artefact-2026-11-02/ARCHITECTURE-SPINE.md
  - _bmad-output/planning-artifacts/architecture/architecture-Desafio tecnico Artefact-2026-11-02/implementation-constraints.md
---

# Desafio tecnico Artefact - Epic Breakdown

## Overview

This document defines a deliberately coarse-grained epic and major-story breakdown for the Empório da Música Trusted AI Assistant. Stories represent substantial delivery slices and should not be split further unless implementation exposes a real independent review boundary.

## Requirements Inventory

### Functional Requirements

- **FR1:** Customers can receive store information, including address, opening hours, product scope, and documented contact discrepancies without invented certainty.
- **FR2:** Customers can ask about payment, shipping, returns, exchanges, and warranty policies using traceable Policy Source sections.
- **FR3:** Customers can receive PIX, installment, and shipping calculations using deterministic currency and policy rules.
- **FR4:** Customers can search Products by natural-language criteria such as category, name, and budget.
- **FR5:** Customers can request exact Product details and snapshot price without fabricated Products or prices.
- **FR6:** Customers can receive valid Promotion information without silently stacking incompatible discounts.
- **FR7:** The system verifies Order ownership using a server-established Authorized Principal.
- **FR8:** An authorized Customer can receive snapshot Order status without live-tracking claims or unnecessary private data.
- **FR9:** Customers can ask follow-up questions within an isolated, bounded Session.
- **FR10:** The Assistant can execute only allowlisted, schema-validated Tools with authorization, timeout, and round-budget controls.
- **FR11:** The Assistant handles unsupported requests, missing data, provider failures, ambiguity, and partial results honestly.
- **FR12:** An optional WhatsApp adapter can normalize, validate, deduplicate, and route messages through the shared conversation service.
- **FR13:** An optional market comparison capability can return provenance-bearing External Offers without changing official Product prices.
- **FR14:** An optional MCP adapter can expose selected use cases while reusing domain rules and authorization.

### NonFunctional Requirements

- **NFR1 Security:** No unauthorized private-data disclosure; Order authorization is server-side.
- **NFR2 Privacy:** Logs and public fixtures exclude raw customer PII by default.
- **NFR3 Determinism:** Product, Promotion, payment, shipping, availability, provenance, and ownership rules remain outside the LLM.
- **NFR4 Reliability:** Tool, provider, retrieval, and external-integration failures have bounded, honest fallbacks.
- **NFR5 Reproducibility:** The P0 suite runs offline with FakeLLM, SQLite, and deterministic fixtures.
- **NFR6 Traceability:** Snapshot and policy answers carry appropriate source provenance and freshness context.
- **NFR7 Portability:** Providers and channels are replaceable through ports and adapters without changing domain behavior.
- **NFR8 Observability:** Structured sanitized events include correlation and tool/provider outcomes without sensitive text by default.
- **NFR9 Language:** Customer-facing responses use clear Brazilian Portuguese with transparent uncertainty.
- **NFR10 Quality:** Automated unit, contract, integration, scenario, and security tests cover success, failure, boundary, and injection cases.

### Additional Requirements

- Use Hexagonal Architecture with inward dependency direction.
- Give each state family one owning service/repository boundary.
- Keep structured operational retrieval separate from section-aware policy retrieval.
- Normalize providers behind `LLMPort` and `LLMFactory`; FakeLLM is mandatory for offline tests.
- Expose only an allowlisted `ToolRegistry`; prohibit arbitrary SQL, shell commands, dynamic imports, and unknown tools.
- Use SQLite as the P0 persistence boundary with atomic, idempotent ingestion.
- Route CLI, HTTP, and future channels through one `ConversationService`.
- Keep WhatsApp, market comparison, and MCP optional and isolated from the P0 path.
- Use `Decimal` for customer-visible money calculations.
- Keep BMAD, Codex, and Ponytail outside runtime dependencies.
- Resolve implementation root, first delivery surface, exact dependency pins, commercial boundaries, and data publication permission before the relevant implementation work.

### UX Design Requirements

No separate UX design contract was found. Customer-facing behavior is defined by the PRD and must remain clear, concise, informal-professional Brazilian Portuguese.

### FR Coverage Map

FR1: Epic 1 - Store information and contact guidance.
FR2: Epic 1 - Policy retrieval and traceable policy answers.
FR3: Epic 1 - Payment and shipping calculations.
FR4: Epic 1 - Product search and availability.
FR5: Epic 1 - Exact Product details and snapshot price.
FR6: Epic 1 - Promotion handling.
FR7: Epic 2 - Server-side Order authorization.
FR8: Epic 2 - Authorized snapshot Order status.
FR9: Epic 2 - Bounded Session context.
FR10: Epic 2 - Allowlisted, validated, bounded Tool execution.
FR11: Epic 2 - Honest limitation and failure handling.
FR12: Epic 3 - Optional WhatsApp channel adapter.
FR13: Epic 3 - Optional market comparison.
FR14: Epic 3 - Optional MCP adapter.

## Epic List

### Epic 1: Discover Products and Understand Store Policies

Customers can find available Products, see exact snapshot prices and Promotions, calculate payment/shipping options, and understand store policies.

**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6

### Epic 2: Securely Manage Conversations and Orders

Customers can maintain context across a Session and authorized Customers can check their own Orders without exposing private information.

**FRs covered:** FR7, FR8, FR9, FR10, FR11

### Epic 3: Run and Extend the Trusted Assistant

Evaluators and developers can run the core system offline, verify its behavior, switch LLM providers, and optionally add external channels or integrations.

**FRs covered:** FR12, FR13, FR14

**Cross-cutting requirements:** NFR1 through NFR10

## Epic 1: Discover Products and Understand Store Policies

Customers can obtain trustworthy store guidance, search available Products, see exact snapshot prices, understand Promotions, and calculate payment/shipping options.

**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6

### Story 1.1: Answer Store and Policy Questions

As a Customer,
I want to ask about store information, payment, shipping, returns, exchanges, and warranty,
So that I can understand the store rules without receiving invented information.

**FRs covered:** FR1, FR2

**Acceptance Criteria:**

**Given** the Policy Source is available
**When** the Customer asks a store or policy question
**Then** the Assistant returns a concise Brazilian Portuguese answer grounded in the relevant policy section
**And** includes source provenance when appropriate.

**Given** the policy content is insufficient or contradictory
**When** the Customer asks a question
**Then** the Assistant states the limitation or asks for relevant context
**And** does not invent a rule.

**Given** the source contains conflicting contact information
**When** the Customer asks for contact details
**Then** the Assistant communicates the discrepancy instead of presenting one value as certain.

### Story 1.2: Search Products and Show Exact Availability

As a Customer,
I want to search available Products by criteria such as category, name, or budget,
So that I can find suitable instruments and know their snapshot price and availability.

**FRs covered:** FR4, FR5

**Acceptance Criteria:**

**Given** the Operational Snapshot has matching Products
**When** the Customer searches by category, name, or budget
**Then** results include only active Products with positive stock when availability is requested
**And** results are bounded, ordered, and paginated.

**Given** a Product exists in the snapshot
**When** the Customer asks for its details or price
**Then** the response uses the stored Product data and formats the price in BRL
**And** identifies the information as snapshot-based when freshness matters.

**Given** no Product matches or the request is ambiguous
**When** the Customer searches
**Then** the Assistant reports no match or asks for clarification
**And** does not fabricate a Product or price.

### Story 1.3: Apply Promotions and Calculate Payment Options

As a Customer,
I want to know the active Promotion and calculate PIX, installments, and shipping,
So that I can understand the effective purchase conditions.

**FRs covered:** FR3, FR6

**Acceptance Criteria:**

**Given** a Product has an active Promotion in the snapshot
**When** the Customer asks for its price or payment options
**Then** the response separates original price, discount, and promotional price
**And** does not stack the PIX discount on top of the Promotion.

**Given** the Product is not under an active Promotion
**When** the Customer asks for PIX
**Then** the documented PIX rule is applied with decimal arithmetic and the declared rounding rule.

**Given** the Customer asks for installments or shipping
**When** the amount falls on a documented or ambiguous boundary
**Then** the applicable rule or explicit assumption is communicated
**And** no unsupported calculation is presented as certain.

## Epic 2: Securely Manage Conversations and Orders

Customers can check their own Orders securely, maintain conversation context, and receive safe responses when tools, data, or providers fail.

**FRs covered:** FR7, FR8, FR9, FR10, FR11

### Story 2.1: Check Authorized Order Status

As an authorized Customer,
I want to check the status of my Order,
So that I can receive useful information without exposing private data.

**FRs covered:** FR7, FR8

**Acceptance Criteria:**

**Given** the server provides an Authorized Principal that owns the Order
**When** the Customer asks the Order status
**Then** the Assistant returns the permitted snapshot status and necessary details
**And** does not claim live tracking.

**Given** the Customer is anonymous, unauthorized, or belongs to another Customer
**When** the Customer asks for an Order
**Then** the Assistant refuses the private details
**And** does not reveal whether the Order exists.

**Given** the Order identifier is malformed or nonexistent
**When** the Customer asks for it
**Then** the response uses a safe non-enumerating outcome.

### Story 2.2: Maintain Safe Multi-Turn Conversation Context

As a Customer,
I want to ask follow-up questions in the same conversation,
So that I do not need to repeat the Product or policy context.

**FRs covered:** FR9

**Acceptance Criteria:**

**Given** a Product or policy topic was identified in the current Session
**When** the Customer asks a follow-up question
**Then** the Assistant uses the relevant context to interpret it correctly.

**Given** two Sessions belong to different users or principals
**When** either Session continues
**Then** history and authorization state remain isolated.

**Given** a Session expires or its storage fails
**When** the Customer sends a new message
**Then** the Assistant starts a safe fresh context
**And** does not restore stale private information.

### Story 2.3: Execute Tools Safely and Handle Failures

As a Customer,
I want the Assistant to use reliable Tools and explain limitations honestly,
So that failures do not become invented answers or unsafe actions.

**FRs covered:** FR10, FR11

**Acceptance Criteria:**

**Given** the Assistant requests a Tool
**When** the Tool is not allowlisted, has invalid arguments, lacks authorization, exceeds its timeout, or exceeds the call budget
**Then** execution is rejected safely
**And** the Customer receives an honest limitation message.

**Given** a Tool, provider, or retrieval operation fails or returns partial data
**When** the Assistant prepares a response
**Then** it reports the unavailable or incomplete information
**And** does not fill missing values by inference.

**Given** the Customer asks for an unsupported action or an unrelated product
**When** the Assistant cannot fulfill the request
**Then** it refuses or redirects clearly
**And** does not claim that an action was completed.

## Epic 3: Run and Extend the Trusted Assistant

Evaluators and developers can run the Assistant offline, verify its safety and behavior, switch providers, and optionally add external integrations.

**FRs covered:** FR12, FR13, FR14

**Cross-cutting requirements:** NFR1 through NFR10

### Story 3.1: Run and Verify the Assistant Offline

As an evaluator or Developer,
I want to run the Assistant locally without external credentials,
So that I can verify its behavior reproducibly.

**NFRs covered:** NFR1, NFR2, NFR4, NFR5, NFR6, NFR8, NFR10

**Acceptance Criteria:**

**Given** a clean supported environment
**When** the documented setup and test commands are executed
**Then** the P0 system runs with SQLite, FakeLLM, and deterministic fixtures
**And** no external credentials are required.

**Given** the core scenario suite is executed
**When** catalog, policy, payment, authorization, injection, failure, and unsupported-action cases run
**Then** the expected results pass
**And** no unauthorized private data is disclosed.

**Given** the Assistant processes requests
**When** observability events are emitted
**Then** correlation, tool/provider outcome, duration, and error information are available
**And** raw prompts and customer PII are excluded by default.

**Given** a provider is configured
**When** it is selected through the supported configuration
**Then** it is validated against the normalized LLM contract and required capabilities
**And** incompatible or missing configuration fails clearly without breaking FakeLLM mode.

### Story 3.2: Add Optional External Integrations

As a Developer,
I want to add optional channels and external capabilities,
So that the Assistant can evolve without changing P0 business rules.

**FRs covered:** FR12, FR13, FR14

**NFRs covered:** NFR3, NFR7

**Acceptance Criteria:**

**Given** the WhatsApp adapter is enabled
**When** a valid or invalid webhook is received
**Then** the adapter validates, normalizes, verifies, and deduplicates messages
**And** routes valid messages through the shared ConversationService.

**Given** market comparison is enabled
**When** the Assistant searches for an exact Product match
**Then** External Offers include source, URL, date, condition, and match information
**And** they remain separate from the official Product price.

**Given** MCP is enabled
**When** a supported MCP operation is requested
**Then** it reuses the same domain use cases and authorization rules
**And** does not duplicate business logic.

**Given** any optional integration is unavailable or fails
**When** a Customer uses the core Assistant
**Then** P0 catalog, policy, payment, and authorized-order behavior remains available
**And** the failure is communicated honestly.
