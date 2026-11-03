---
title: 'Story 1.3 - Apply Promotions and Calculate Payment Options'
type: 'feature'
created: '2026-11-03'
status: 'done'
baseline_commit: '9ff507c3adf91fd47bda303240d16addfde46329'
route: 'dispatch'
review_loop_iteration: 0
context:
  - E:/Desafio tecnico Artefact/_bmad-output/implementation-artifacts/epic-1-context.md
  - E:/Desafio tecnico Artefact/_bmad-output/planning-artifacts/architecture/architecture-Desafio tecnico Artefact-2026-11-02/ARCHITECTURE-SPINE.md
  - E:/Desafio tecnico Artefact/artefact_architecture_v2_ponytail/artefact_architecture_v2_ponytail/AGENTS.md
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** Customers need trustworthy purchase-condition answers, but promotional prices, PIX discounts, installment values, and shipping boundaries must be calculated from deterministic snapshot facts without silently stacking discounts or inventing commercial rules.

**Approach:** Extend the catalog boundary with validated promotion ingestion and a deterministic payment service that returns original price, applicable promotion, PIX outcome, installments, and shipping as separate traceable components. Reuse the existing CLI and SQLite snapshot instead of adding an LLM or external provider.

## Boundaries & Constraints

**Always:** Use active Promotion rows from the Operational Snapshot only; treat `is_active` as active in the snapshot, not guaranteed current today; preserve original and discounted amounts; use Decimal with banker’s rounding to BRL cents; apply the 5% PIX rule only when no promotion applies; for installments use the section 3.1 bands (1–3x except purchases below R$50, 4–6x with R$80 minimum per installment, 7–12x with R$100 minimum per installment); charge R$35 shipping for orders at or below R$500 and no shipping charge above R$500; reject or flag multiple active promotions rather than summing them; keep product/promotion/payment/shipping rules outside the LLM; expose assumptions for unresolved policy boundaries.

**Never:** Do not combine PIX with a promotional discount; do not treat seasonal PDF language as proof of an active promotion; do not use floating-point arithmetic, live pricing, external market data, orders, or arbitrary SQL; do not claim shipping or installment rules as authoritative where the source remains ambiguous.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| ACTIVE_PROMOTION | Valid product with one active snapshot promotion | Return list price, discount percentage/value, and promotional price | Mark promotion as snapshot-based |
| PROMOTION_PIX | Promoted product and PIX requested | Keep promotional price; do not apply the additional 5% PIX discount | Explain non-stacking rule |
| NON_PROMOTIONAL_PIX | Valid product without active promotion and PIX requested | Apply exactly 5% to list price with declared BRL rounding | Return deterministic amount |
| INSTALLMENTS | Valid amount and installment count from 1 to 12 | Return equal installment values or explicit documented limitation by band | Reject invalid count and preserve Decimal arithmetic |
| SHIPPING_BOUNDARY | Amount at or below, or above R$500 | Apply R$35 at or below R$500; free only above R$500 | Return the deterministic boundary rule |
| MULTIPLE_PROMOTIONS | Product has more than one active promotion | Do not sum discounts or select silently | Flag the product as ambiguous/unavailable for automatic price calculation |
| INVALID_PROMOTION | Negative, over-100%, malformed, or non-finite discount | Reject the source record atomically | Preserve the prior valid snapshot |

</frozen-after-approval>

## Code Map

- `src/emporio/catalog.py`, `src/emporio/catalog_repository.py`, `src/emporio/catalog_sqlite.py` -- completed Product snapshot boundary; extend with Promotion facts and preserve atomic ingestion/query conventions.
- `src/emporio/catalog_service.py` -- completed deterministic product use cases; reuse product lookup and snapshot metadata without duplicating SQL.
- `src/emporio/cli.py` -- existing policy and catalog delivery surface; add promotion/payment options while keeping error handling separated by domain.
- `Desafio_Técnico_AI_Engineer_2026-20260616T150750Z-3-001/.../data/desafio_tecnico_ai_eng - promotions.csv` -- ignored local promotion source; never commit raw challenge data.
- `artefact_architecture_v2_ponytail/artefact_architecture_v2_ponytail/DATA_MODEL.md` -- promotion, PIX, and multi-promotion constraints.
- `E:/Desafio tecnico Artefact/_bmad-output/implementation-artifacts/epic-1-context.md` -- Epic 1 requirements and Story 1.2 dependency.

## Tasks & Acceptance

**Execution:**
- [x] `src/emporio/catalog.py` -- define Promotion and payment result/value objects plus typed calculation errors -- keep money and commercial facts deterministic.
- [x] `src/emporio/catalog_repository.py` -- extend the repository contract for promotions and product-price lookup -- keep structured operational retrieval behind a port.
- [x] `src/emporio/catalog_sqlite.py` -- validate and atomically ingest promotion rows and query active promotions -- reject invalid discounts and duplicate/ambiguous source records.
- [x] `src/emporio/payment_service.py` -- calculate promotions, PIX, installments, and shipping with Decimal and explicit assumptions -- prevent discount stacking and unsupported certainty.
- [x] `src/emporio/cli.py` -- expose promotion/payment queries in Brazilian Portuguese -- show original, discount, effective, installment, and shipping components clearly.
- [x] `tests/` -- cover promotion application, PIX non-stacking, non-promotional PIX, installment boundaries, shipping boundary, multiple promotions, invalid ingestion, and rounding -- remain offline and deterministic.

**Acceptance Criteria:**
- Given an active Promotion in the snapshot, when a product price or payment option is requested, then original price, discount, and promotional price are separated and PIX is not stacked on top.
- Given no active Promotion, when PIX is requested, then the documented 5% rule is applied with Decimal arithmetic and the approved rounding rule.
- Given an installment or shipping request on a documented or ambiguous boundary, when the payment service responds, then it applies the approved rule or states the assumption explicitly without presenting unsupported certainty.
- Given invalid or multiple active promotion records, when ingestion or calculation runs, then the data is rejected or flagged and no summed or silently selected discount is returned.
- Given the payment tests run in a clean local environment, when they execute, then they pass with temporary SQLite and no network credentials or LLM provider.

## Implementation Notes

Implemented validated promotion ingestion, deterministic promotion/payment calculations, banker’s rounding, non-stacking PIX behavior, section 3.1 installment bands, effective-total shipping rules, explicit promotion provenance, and a Portuguese CLI payment action. Payment options now require an available product and reject mixed PIX/installment requests. Installment rounding reconciles the final centavo when equal displayed installments cannot sum exactly.

## Spec Change Log

Empty at planning time.

## Review Triage Log

- `medium (patch)` -- Added CLI payment coverage for original price, promotion discount, effective price, PIX non-stacking, shipping, and snapshot output.
- `medium (patch)` -- Corrected payment CLI mojibake and added promotion description/ID plus snapshot provenance.
- `medium (patch)` -- Reconciled rounded installments with an adjusted final installment so the displayed schedule sums to the effective amount.
- `medium (patch)` -- Shipping now uses the effective order total, so a promotional price determines the R$500 boundary consistently; PIX does not change shipping eligibility.
- `medium (patch)` -- Payment rejects unavailable products and validates promotion activity, product identity, and discount bounds at the service boundary.
- `medium (patch)` -- Added regression coverage for promotional rounding and shipping after discount.
- `maybe-false (defer)` -- A concurrent snapshot replacement could combine a product and promotions from different repository reads; reproduce under concurrent ingestion before introducing a transaction-scoped repository API.
- `false` -- The claimed zero-value PIX fallback is prevented by an explicit `is not None` check.
- `false` -- Active promotions are intentionally returned in deterministic promotion-ID order, which is the repository contract; source-row ordering is not required by the approved intent.

## Design Notes

Promotion application precedes payment calculation. A payment result should retain enough component detail for the CLI to explain why a PIX discount was or was not applied; it must not expose raw CSV rows or policy documents.

## Verification

**Commands:**
- `uv run pytest -q` -- expected: policy, catalog, and payment tests pass offline.
- `uv run --with ruff ruff check src tests` -- expected: no lint findings in implementation or tests.
- `python -m compileall -q src tests` -- expected: no syntax errors.
