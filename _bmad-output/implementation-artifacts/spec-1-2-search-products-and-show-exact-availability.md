---
title: 'Story 1.2 - Search Products and Show Exact Availability'
type: 'feature'
created: '2026-11-02'
status: 'done'
baseline_commit: '3745f2b196cc52e768f782af536c44e8bf3a1969'
route: 'dispatch'
review_loop_iteration: 0
context:
  - E:/Desafio tecnico Artefact/_bmad-output/implementation-artifacts/epic-1-context.md
  - E:/Desafio tecnico Artefact/_bmad-output/planning-artifacts/architecture/architecture-Desafio tecnico Artefact-2026-11-02/ARCHITECTURE-SPINE.md
  - E:/Desafio tecnico Artefact/artefact_architecture_v2_ponytail/artefact_architecture_v2_ponytail/AGENTS.md
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** Customers need to find suitable instruments and see exact snapshot prices and availability without the assistant inventing products, prices, or live-stock claims.

**Approach:** Add a deterministic operational-snapshot catalog slice behind typed repository boundaries, with validated CSV ingestion into SQLite and a CLI search/detail surface that supports natural-language name, category, and budget criteria.

## Boundaries & Constraints

**Always:** Treat the supplied CSVs as a dated Operational Snapshot, not live inventory; preserve source product IDs; use the ingestion timestamp as `data_as_of`; use Decimal-safe BRL handling; include only valid products in customer answers; apply `status=active` and `stock_quantity>0` when availability is requested; return bounded, deterministic ordering and pagination; separate catalog retrieval from the Policy Source; keep SQL parameterized and ingestion atomic.

**Never:** Do not use an LLM, fuzzy ungrounded facts, arbitrary SQL, live ERP calls, promotion calculation, payment calculation, order data, or external market data in this story. Do not claim real-time stock or fabricate a match when the query is ambiguous or unsupported.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| AVAILABLE_SEARCH | Active products with positive stock and a category/name/budget query | Bounded Portuguese results with exact BRL snapshot prices and availability | Apply deterministic ordering and page bounds |
| UNAVAILABLE_PRODUCT | Inactive or zero-stock product matches the text | Exclude it when availability is requested | Do not describe it as available |
| EXACT_DETAIL | One valid product matches by ID or unambiguous name | Return stored name, description/specs, price, stock/status, and snapshot freshness | No recalculation or invented field |
| NO_MATCH | No valid product satisfies the criteria | Honest no-match response | Never fabricate a product or price |
| AMBIGUOUS_QUERY | Multiple products match an underspecified name | Ask for a narrowing criterion or return bounded candidates | Do not select one silently |
| INVALID_SOURCE | CSV has invalid monetary, stock, status, duplicate-ID, or malformed required data | Reject the ingestion atomically | Preserve the prior valid snapshot and expose a typed error |

</frozen-after-approval>

## Code Map

- `src/emporio/policy.py`, `src/emporio/ports.py`, `src/emporio/service.py` -- completed policy slice; reuse the typed-error and delivery conventions without mixing policy retrieval with catalog facts.
- `src/emporio/cli.py` -- existing first delivery surface; extend with a catalog command or dispatch path while preserving the policy command.
- `pyproject.toml` -- package and test configuration; add only required SQLite/catalog dependencies.
- `Desafio_Técnico_AI_Engineer_2026-20260616T150750Z-3-001/.../data/desafio_tecnico_ai_eng - products.csv` -- local product source; keep ignored and never commit raw challenge data.
- `artefact_architecture_v2_ponytail/artefact_architecture_v2_ponytail/DATA_MODEL.md` -- verified product fields, validity rules, availability formula, and snapshot caveats.
- `E:/Desafio tecnico Artefact/_bmad-output/implementation-artifacts/epic-1-context.md` -- Epic 1 requirements and cross-story dependency rules.

## Tasks & Acceptance

**Execution:**
- [x] `src/emporio/catalog.py` -- define Product, search criteria, snapshot metadata, and typed catalog errors -- keep operational facts independent of SQL and CLI concerns.
- [x] `src/emporio/catalog_repository.py` -- define the typed repository port and deterministic query contract -- prevent arbitrary SQL and preserve source IDs.
- [x] `src/emporio/catalog_sqlite.py` -- validate and atomically ingest product/category CSV data into SQLite and query bounded results -- reject invalid records rather than silently normalizing them.
- [x] `src/emporio/catalog_service.py` -- apply availability, exact-detail, no-match, ambiguity, ordering, and pagination rules -- keep all catalog facts deterministic.
- [x] `src/emporio/cli.py` -- expose catalog search and detail requests in Brazilian Portuguese while preserving the existing policy path -- provide snapshot freshness context.
- [x] `tests/` -- cover valid ingestion, invalid atomic rejection, active/stock filtering, exact BRL output, no-match, ambiguity, and pagination -- keep tests offline with temporary SQLite.

**Acceptance Criteria:**
- Given a valid Operational Snapshot, when a category, name, or maximum-budget search is submitted, then results are bounded, deterministic, ordered, paginated, and contain only active products with positive stock when availability is requested.
- Given an unambiguous product in the snapshot, when details or price are requested, then the response uses stored fields, formats BRL exactly, and identifies the data as snapshot-based rather than live.
- Given no match, an ambiguous query, or an invalid product record, when the catalog service responds, then it returns a safe no-match/clarification outcome and never invents product data.
- Given invalid source data, when ingestion runs, then the transaction is rejected atomically and no partial invalid snapshot becomes queryable.
- Given the catalog tests run in a clean local environment, when they execute, then they pass with temporary SQLite and no network credentials or LLM provider.

## Implementation Notes

Implemented a deterministic SQLite catalog slice with validated CSV ingestion, atomic snapshot replacement, preserved product IDs, Decimal prices, stable ordering, bounded pagination, availability filtering, exact details, ambiguity/no-match handling, and a Portuguese CLI catalog surface. `data_as_of` is captured at ingestion time. Tests use temporary SQLite databases and do not access the ignored challenge data.

## Spec Change Log

Empty at planning time.

## Review Triage Log

- `medium (patch)` -- Detail rendering now includes stored `specs`; the prior CLI output omitted a required exact-detail field.
- `medium (patch)` -- Non-finite and negative budgets are rejected before SQL filtering.
- `medium (patch)` -- Naive `data_as_of` values are converted to typed ingestion errors rather than escaping as `ValueError`.
- `medium (patch)` -- Duplicate, extra, and malformed CSV columns/rows are rejected instead of being silently discarded.
- `medium (patch)` -- Status values are validated exactly, without lowercasing invalid source values.
- `low (patch)` -- Literal `%`, `_`, and backslash search criteria are escaped for SQLite `LIKE` matching.
- `medium (patch)` -- Catalog CLI failures now use catalog-specific safe wording and catch invalid SQLite connections.
- `medium (patch)` -- Added focused coverage for budget boundaries, pagination, detail delivery, invalid records, categories, and rollback.
- `medium (patch)` -- Extreme Decimal quantization failures are converted to `CatalogIngestionError`.
- `medium (patch)` -- `created_at` is validated as ISO-8601 before ingestion.
- `maybe-false (defer)` -- A concurrent snapshot replacement could theoretically mix rows and metadata because reads are not held in one explicit transaction; reproduce with concurrent ingestion before changing the repository contract.
- `maybe-false (defer)` -- SQLite `LOWER()` Unicode case behavior may miss accented case variants; settle with a supported-runtime query matrix before adding a normalization column.
- `false` -- The cited missing-description row crash is prevented by row-shape validation before field access.
- `false` -- The cited catalog database traceback is prevented by the repository connection error boundary and CLI `CatalogError` branch.
- `false` -- The cited missing budget, pagination, detail, invalid-source, category, and rollback evidence has been covered by the added tests, all of which passed.

## Design Notes

Use an explicit structured query model even when the first CLI accepts natural-language text. Default result ordering should be stable and documented; future HTTP or tool adapters must call the same catalog service rather than reimplementing filtering.

## Verification

**Commands:**
- `uv run pytest -q` -- expected: policy and catalog tests pass offline.
- `uv run --with ruff ruff check src tests` -- expected: no lint findings in implementation or tests.
- `python -m compileall -q src tests` -- expected: no syntax errors.
