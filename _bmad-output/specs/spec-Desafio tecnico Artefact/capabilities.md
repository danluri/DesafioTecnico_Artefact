# Capability Matrix

| Capability | Primary boundary | Required behavior |
|---|---|---|
| CAP-1 | Policy retrieval and conversation | Section-aware policy answers, provenance, uncertainty handling, Brazilian Portuguese |
| CAP-2 | Catalog domain and repository | Active/in-stock filtering, bounded search, exact snapshot price |
| CAP-3 | Payment/promotion domain services | Decimal arithmetic, non-stacking rules, explicit boundary assumptions |
| CAP-4 | Order use case and authorization | Server principal, ownership check, non-enumerating denial |
| CAP-5 | Conversation and session services | Isolated bounded context, follow-up continuity, safe expiry |
| CAP-6 | Tool registry and orchestrator | Allowlist, schema validation, authorization, timeout, round budget |
| CAP-7 | Local runtime and test harness | FakeLLM, SQLite, fixtures, no credentials for core suite |
| CAP-8 | LLM port and adapters | Normalized messages/results/capabilities, provider contract tests |
| CAP-9 | Scenario and security tests | Negative cases, provenance, failure, injection, unsupported action |
| CAP-10 | Optional adapters | Reuse P0 use cases; no P0 dependency or official-price mutation |

## Traceability to PRD

- CAP-1 → FR-1, FR-2, FR-3
- CAP-2 → FR-4, FR-5
- CAP-3 → FR-3, FR-6
- CAP-4 → FR-7, FR-8
- CAP-5 → FR-9
- CAP-6 → FR-10, FR-11
- CAP-7 → P0 reproducibility requirements and SM-3
- CAP-8 → FR-10 and SM-6
- CAP-9 → FR-11 and SM-1 through SM-4
- CAP-10 → FR-12 through FR-14
