# Architecture Input Reconciliation

## PRD and addendum

- FR-1 through FR-3 map to PolicyRetriever, policy provenance, and deterministic payment/shipping services.
- FR-4 through FR-6 map to domain catalog/promotion services and typed SQLite repositories.
- FR-7 and FR-8 map to Authorized Principal and the Order use case; the architecture does not treat chat identity as authentication.
- FR-9 through FR-11 map to ConversationService, SessionRepository, ToolRegistry, bounded orchestration, and safe fallback.
- FR-12 through FR-14 remain optional adapters and do not enter the P0 dependency path.
- The P0/P1 boundary, privacy constraints, snapshot freshness, and offline reproducibility are represented as ADs or conventions.

## Existing architecture and ADRs

- Ports & Adapters is retained as the named paradigm.
- ADR-001 is represented by AD-5; ADR-002 by AD-4; ADR-003 by AD-10; ADR-004 by the deferred/runtime boundary and is not a product dependency.
- The existing context and sequence diagrams were reduced to a structural seed so the spine fixes relationships without becoming a second implementation manual.

## Roadmap and test strategy

- Foundation, data tools, retrieval, agent MVP, and hardening are represented in AD-9, AD-12, and AD-13.
- Contract, domain, integration, scenario, security, and offline test layers are preserved by AD-13.
- WhatsApp, market intelligence, and MCP remain after P0 stabilization as required by the roadmap.

## Gaps intentionally left open

- Implementation root, exact dependency pins, first delivery surface, real provider, and public-data permission remain deferred because they do not change the architecture paradigm or P0 ownership rules.
