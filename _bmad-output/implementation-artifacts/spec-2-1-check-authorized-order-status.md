---
title: 'Story 2.1 - Check Authorized Order Status'
type: 'feature'
created: '2026-11-03'
status: 'done'
baseline_commit: '2f1e98990ddf7e3ebe3e9fd015a933d3327795bc'
route: 'dispatch'
review_loop_iteration: 0
context:
  - E:/Desafio tecnico Artefact/_bmad-output/implementation-artifacts/epic-2-context.md
  - E:/Desafio tecnico Artefact/_bmad-output/planning-artifacts/architecture/architecture-Desafio tecnico Artefact-2026-11-02/ARCHITECTURE-SPINE.md
  - E:/Desafio tecnico Artefact/_bmad-output/planning-artifacts/prds/prd-Desafio tecnico Artefact-2026-11-02/prd.md
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** Customers need useful order-status information, but an order identifier or identity claim in conversation text must never authenticate a customer or reveal whether another customer's order exists.

**Approach:** Add a deterministic Order status use case backed by the existing SQLite operational snapshot. The application receives a server-established `AuthorizedPrincipal`, proves ownership in the repository query, and returns only a bounded, snapshot-based order view. Reuse the existing CLI as a local demonstration seam; it must make the principal boundary explicit and must not imply production authentication.

## Boundaries & Constraints

**Always:** Require an explicit `AuthorizedPrincipal` for private order reads; preserve source order/customer IDs internally; query with parameterized SQL; ingest customers, orders, and order items atomically; return status, order date, total, payment method, permitted delivery estimate, and bounded item summaries when ownership is proven; include snapshot provenance and state that it is not live tracking; use typed errors and safe non-enumerating responses; keep customer PII out of returned views and logs; run offline with SQLite fixtures.

**Never:** Never authenticate from order ID, name, phone, e-mail, or chat text; never disclose whether an order exists to anonymous, malformed, nonexistent, or cross-customer requests; never expose raw customer rows, notes, tracking identifiers, SQL, stack traces, or full source payloads; never claim live delivery tracking; never add a remote provider or production authentication dependency.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| AUTHORIZED_OWNER | Valid principal owns the order | Return bounded status snapshot, date, total, payment method, permitted delivery estimate/items, and `data_as_of` | Deterministic success |
| ANONYMOUS | No principal supplied | Refuse private details without existence signal | Safe authorization response |
| CROSS_CUSTOMER | Principal does not own the requested order | Same safe response as nonexistent order | Do not reveal ownership or existence |
| MALFORMED_ID | Empty, non-integer, negative, or oversized order reference | Safe non-enumerating response | Typed validation error mapped to generic message |
| NONEXISTENT_ID | Valid identifier absent from snapshot | Same safe response as unauthorized order | No existence signal |
| MISSING_OPTIONAL_DATA | Owned order lacks tracking or estimated delivery | Return status and available fields; state tracking is unavailable | Never invent a value or claim live tracking |
| INVALID_SOURCE | Duplicate/orphan/malformed customer, order, or item row | Reject the complete ingestion | Preserve previous valid snapshot atomically |

## Code Map

- `src/emporio/order.py` -- add `AuthorizedPrincipal`, bounded order/item snapshot value objects, and typed order/authorization errors.
- `src/emporio/order_repository.py` -- define the typed read-only repository port for authorized order lookup and snapshot metadata.
- `src/emporio/order_service.py` -- enforce input validation, ownership semantics, safe result mapping, and non-enumerating outcomes outside SQLite.
- `src/emporio/catalog_sqlite.py` or a focused SQLite adapter -- validate and atomically ingest the customer/order/order-item CSVs and execute ownership-filtered parameterized queries without leaking PII.
- `src/emporio/cli.py` -- expose a bounded `order-status` action using an explicitly documented server-principal demo argument and Portuguese safe responses.
- `tests/` -- cover owner success, anonymous/cross-customer/nonexistent equivalence, malformed IDs, missing tracking, ingestion integrity, snapshot provenance, and CLI output privacy.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- record only review-confirmed follow-up work; do not place raw challenge CSVs under version control.

## Tasks & Acceptance

**Execution:**
- [x] Define order domain types, `AuthorizedPrincipal`, safe result shape, and typed errors.
- [x] Extend the SQLite snapshot boundary with validated customer/order/item ingestion and ownership-filtered reads.
- [x] Implement the Order status service with authorization before private-data mapping and no enumeration side channel.
- [x] Add the CLI delivery seam and explicit snapshot/non-live wording without treating CLI input as production authentication.
- [x] Add deterministic unit, integration, security, and CLI tests for every matrix case.

**Acceptance Criteria:**
- Given the server provides an `AuthorizedPrincipal` that owns an order, when status is requested, then the service returns only the permitted snapshot fields and clearly states that it is not live tracking.
- Given no principal, a different principal, a malformed identifier, or an absent order, when status is requested, then the response is safe and equivalent with no indication that the order exists or belongs to someone else.
- Given source data is malformed, duplicated, orphaned, or inconsistent, when ingestion runs, then the complete order snapshot is rejected and the previous valid snapshot remains available.
- Given optional tracking/delivery data is absent, when an authorized status is requested, then the response reports that the information is unavailable and does not infer a value.
- Given the offline test suite runs, when order-status scenarios execute, then all tests pass with temporary SQLite, deterministic fixtures, and no credentials or network calls.

## Implementation Notes

The source fixture currently contains customer PII and must remain ignored/local. Tests should use anonymized synthetic rows. A server-established principal is represented as an application input to the use case; the local CLI flag is only a demonstration seam and must be named/documented accordingly. The first implementation should avoid introducing sessions or LLM orchestration, which belong to Stories 2.2 and 2.3.

## Spec Change Log

- Added authorized order snapshot retrieval, atomic source validation, and explicit demo-principal CLI delivery.
- Rejected mixed catalog/order refreshes, validated order-only item references against the catalog, and separated order snapshot provenance from catalog provenance.

## Review Triage Log

- `high (patch)` -- Prevented catalog-only ingestion from leaving orders attached to a different catalog snapshot.
- `high (patch)` -- Prevented orphan order items during order-only ingestion.
- `medium (patch)` -- Added runtime principal validation and independent order snapshot metadata.
- `medium (defer)` -- A fully immutable versioned snapshot/read transaction remains future work; the current P0 boundary rejects mixed refreshes and keeps order reads bounded.

## Design Notes

The repository query should filter by both `order_id` and the principal's customer identity so unauthorized and nonexistent orders follow the same result path. The response may include item product IDs and quantities, but not customer contact fields or free-text order notes. Tracking codes are treated as private delivery data and should be omitted from the P0 response unless the approved implementation demonstrates a clear need; estimated delivery may be returned only when present and must retain snapshot wording.

## Verification

**Commands:**
- `uv run pytest -q` -- expected: policy, catalog, payment, and order-status tests pass offline.
- `uv run --with ruff ruff check src tests` -- expected: no lint findings.
- `python -m compileall -q src tests` -- expected: no syntax errors.

</frozen-after-approval>
