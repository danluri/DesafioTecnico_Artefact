# Edge-Case Review — Empório da Música Trusted AI Assistant

- Product search does not explicitly define behavior for empty, malformed, or contradictory filters; define validation and clarification behavior in the implementation contract.
- Policy retrieval does not explicitly define behavior when no passage reaches the retrieval threshold; require an insufficient-evidence response.
- Session context does not explicitly define behavior after expiration or storage failure; define a fresh-session fallback without leaking prior context.
- Order lookup does not explicitly define behavior for an invalid, malformed, or nonexistent order identifier; use the same non-enumerating response as unauthorized access.
- Tool orchestration does not explicitly define behavior when a tool returns partial data; mark the response incomplete rather than filling missing fields.
- Provider configuration does not explicitly define behavior when the selected provider is missing credentials; fail with an actionable configuration error while keeping fake mode available.
- Catalog pagination does not explicitly define behavior for invalid page size or page token; clamp or reject with a documented limit.
- Promotion handling does not explicitly define behavior when discount data is null, negative, or above 100%; reject invalid records during ingestion.
- Policy source provenance does not explicitly define behavior when page or document version metadata is missing; do not present the answer as fully traceable.
- External-offer comparison does not explicitly define behavior for duplicate offers from one retailer; define independent-source counting.
