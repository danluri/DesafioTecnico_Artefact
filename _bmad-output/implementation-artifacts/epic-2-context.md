# Epic 2 Context: Securely Manage Conversations and Orders

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Enable customers to continue a safe, bounded conversation and retrieve their own order status without exposing private information. The epic must enforce authorization at the server/application boundary, keep session state isolated, constrain model-driven tool use, and communicate missing data, failures, ambiguity, and unsupported actions honestly. Customer-facing responses remain concise, informal-professional Brazilian Portuguese and must distinguish snapshot information from live status.

## Stories

- Story 2.1: Check Authorized Order Status
- Story 2.2: Maintain Safe Multi-Turn Conversation Context
- Story 2.3: Execute Tools Safely and Handle Failures

## Requirements & Constraints

- Order access requires a server-established `AuthorizedPrincipal`; an order ID, name, phone number, or e-mail supplied in conversation text is never authentication.
- Return order information only after proving ownership. Anonymous, unauthorized, cross-customer, malformed, and nonexistent-order requests must use safe non-enumerating outcomes and must not reveal whether an order exists.
- Expose only the minimum necessary snapshot order details. Never claim live tracking; report unavailable tracking data rather than inventing it.
- Sessions are isolated by user/principal and contain bounded history. Follow-ups may use current-session product, policy, or clarification context, but sessions must not share history or authorization state.
- Expired or unavailable session storage must create a fresh safe context and must not restore stale private information implicitly.
- The assistant may execute only named, allowlisted tools with schema-validated arguments, server-side authorization checks, timeouts, and a maximum-round/call budget. Arbitrary SQL, shell commands, dynamic imports, and unknown tools are prohibited.
- Tool, provider, retrieval, and storage failures; partial results; missing fields; unsupported requests; and unrelated-product requests must produce explicit limitations or redirects, never inferred values or claims of completed actions.
- P0 must run reproducibly offline with SQLite, deterministic/anonymized fixtures, and `FakeLLM`, without external credentials. Automated coverage must include success, failure, boundary, authorization, privacy, prompt-injection, ambiguity, and unsupported-action cases.
- Logs and observability must be sanitized by default: retain correlation and outcome information, but exclude raw prompts, customer PII, and full sensitive payloads.

## Technical Decisions

- Use hexagonal architecture with inward dependency direction. Delivery channels call one `ConversationService`; domain/application code must not depend on web frameworks, database libraries, or provider SDKs.
- Keep deterministic order ownership, snapshot status, session, and safety rules outside the LLM. The LLM may request a tool but cannot author returned facts or authorization decisions.
- Use an `Order` use case/service with an injected `AuthorizedPrincipal` and a read-only P0 order repository. Enforce authorization for every private-data adapter, including non-HTTP channels.
- Use a `SessionRepository` as the single owner of session state, with opaque internal session/message identifiers. Do not use customer identifiers as public session identifiers.
- Normalize model providers behind `LLMPort` and `LLMFactory`; normalize messages, tool calls/results, usage, and capabilities. Validate required provider capabilities before execution, while keeping `FakeLLM` on the same contract.
- Expose tools through a stable `ToolRegistry` of named schemas and map typed internal errors to safe delivery responses. Do not expose stack traces, provider payloads, SQL, or private existence details.
- Persist P0 state in SQLite behind ports, using parameterized queries and atomic validated ingestion. Use typed repositories for structured data; policy retrieval remains a separate bounded, provenance-bearing path.
- Emit structured events with correlation ID, hashed session ID, provider/model, tool name, duration, success, error class, and cache status, while excluding sensitive content by default.

## Cross-Story Dependencies

- Story 2.1 depends on the server/session boundary injecting the `AuthorizedPrincipal`, the order repository, and snapshot provenance. Authorization must remain independent of the conversation channel.
- Story 2.2 provides the session isolation and continuity used by order authorization and tool orchestration; session expiration/storage failure must fail closed for private context.
- Story 2.3 depends on the tool registry, normalized LLM boundary, application error policy, and session service. Its timeout and round limits protect both order access and multi-turn conversations.
- All three stories share `ConversationService`, SQLite persistence, sanitized observability, and offline `FakeLLM` scenario/contract tests. Optional WhatsApp and MCP adapters must reuse these boundaries and must not become P0 dependencies.
