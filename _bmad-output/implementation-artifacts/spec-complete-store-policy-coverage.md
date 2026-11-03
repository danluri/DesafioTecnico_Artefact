---
title: 'Complete operational coverage of store policies'
type: 'feature'
created: '2026-11-03'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '468d99322d6ab5a01b80d184ecff0d5717d28a40'
context: []
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** The store policy PDF contains rules that are currently only partially represented: real snapshot ingestion rejects debit orders, local and out-of-region delivery differ, payment combinations are absent, and WhatsApp/post-sale flows are not operationally modeled. Customer-facing Portuguese also contains encoding corruption.

**Approach:** Complete the policy boundary with deterministic offline behavior. Accept debit orders; add package dimensions and weight plus a policy-driven out-of-Campo-Grande shipping analysis that can return Correios/Jadlog options or a special quote; calculate market-style PIX-plus-card combinations above R$2,000; connect the simulated WhatsApp channel to `ConversationService` and `FakeLLM`; add a fake Correios code generator; store complaints in SQLite with documented future analysis; generate return instructions/codes; and normalize customer-facing text and Correios code validation.

**Always:** Keep real Correios/Meta calls disabled by default, label simulated outputs, preserve server-side order authorization, use deterministic Decimal calculations, keep policy provenance, and make missing data explicit.

**Never:** Claim a live carrier lookup, send real WhatsApp messages, invent freight quotes without package data, expose private order data, or treat LLM output as authority over prices, stock, shipping, payment, eligibility, or complaint state.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| DATA_IMPORT | Order uses `debit` | Full supplied snapshot ingests atomically | Invalid rows still roll back |
| LOCAL_SHIPPING | Campo Grande, total <= R$500 or > R$500 | R$35 or free according to policy | Unknown destination is not treated as local |
| REMOTE_SHIPPING | CEP, package weight and dimensions | Deterministic simulated PAC/SEDEX/Jadlog analysis with deadline, insurance and tracking; large package requires quote | Missing dimensions/CEP returns explicit incomplete-data response |
| PAYMENT_COMBO | Eligible total above R$2,000 | PIX plus card installment options, without stacking PIX on promotional price | Invalid split or ineligible total is rejected |
| WHATSAPP_MOCK | Generated inbound message | Same normalized message reaches `ConversationService` and `FakeLLM` response returns | Duplicate message is not processed twice |
| POST_SALE | Complaint, return or warranty question | Complaint persisted; return code/instructions generated; policy answer cites source | Missing order ownership or policy context stays safe |

</frozen-after-approval>

## Code Map

- `src/emporio/catalog_sqlite.py` -- accept the policy payment method `debit` and add validated package fields without breaking atomic ingestion.
- `src/emporio/payment_service.py` -- preserve PIX/promotion rules and add deterministic eligible payment combinations.
- `src/emporio/correios.py` and `src/emporio/simulators.py` -- validate `BR` + 9 alphanumeric characters + `BR` and generate fake carrier codes/results only.
- `src/emporio/whatsapp.py`, `src/emporio/conversation.py`, `src/emporio/llm.py` -- connect the mock channel to the shared conversation path and FakeLLM.
- `src/emporio/` SQLite repositories/services -- add complaint persistence and return-instruction generation behind explicit ownership checks.
- `README.md` and tests -- document policy decisions and cover all new deterministic paths; do not add live provider credentials or network requirements.

## Tasks & Acceptance

**Execution:**
- [x] Update schemas, ingestion fixtures, and migrations for debit and package weight/dimensions.
- [x] Implement remote shipping analysis, payment combinations, standard Correios code generation, complaint storage, and return instructions.
- [x] Wire simulated WhatsApp through `ConversationService` and `FakeLLM`; normalize customer-facing encoding.
- [x] Add policy-driven unit, integration, authorization, persistence, and failure tests; update documentation.

**Acceptance Criteria:**
- Given the supplied CSV snapshot, when all data is ingested, then debit orders are accepted and the transaction remains atomic.
- Given a destination and complete package data, when shipping is analyzed, then the response distinguishes local policy, simulated carrier options, insurance/tracking, and special quotes.
- Given an eligible purchase above R$2,000, when payment options are calculated, then PIX-plus-card combinations are returned without double-discounting.
- Given a generated WhatsApp message, when the mock channel delivers it, then the shared conversation service and FakeLLM produce a deterministic response and duplicates are suppressed.
- Given an authorized complaint or return request, when it is processed, then the complaint is stored or a return code with instructions is generated without exposing unauthorized order data.
- Given malformed text or tracking codes, when processed, then output is valid Brazilian Portuguese and invalid input fails safely.

## Implementation Notes

- Added `debit` and `boleto` to the accepted snapshot payment methods; the supplied CSV set now ingests atomically with 65 products, 50 customers, 20 orders, and 22 order items.
- Added optional package weight/dimension columns, deterministic remote shipping analysis, payment combinations, strict `BR` + 9 alphanumeric characters + `BR` tracking validation, and a fake code generator.
- Added simulated WhatsApp delivery through the real webhook adapter, `ConversationService`, and `FakeLLM`; complaints and authorized return instructions persist through SQLite.
- Customer-facing boundaries now normalize common UTF-8/Latin-1 corruption. Policy retrieval remains deterministic lexical retrieval over PDF pages with provenance; this project does not use vector or embedding-based RAG.
- Real Correios and Meta calls remain disabled by default; carrier estimates and WhatsApp messages are explicitly synthetic.

## Verification

**Commands:**
- `python -m pytest -q` -- passed: 119 tests passed, 1 skipped.
- `uv run --with ruff ruff check src tests` -- passed: no lint errors.
- `python -m compileall -q src tests` -- passed: compilation succeeded.
- Original supplied CSV snapshot ingestion -- passed: all catalog, order, and item rows ingested atomically.

## Review Triage Log

- Correios tracking shape follows the approved store PDF (`BR` + 9 alphanumeric characters + `BR`), so the contrary external-format concern is not applicable to this project policy.
- Return requests intentionally generate a code and instructions behind authorization; the service does not invent receipt dates or final eligibility. The seven-day/product-condition check remains an operational/manual decision until those fields exist in the order snapshot.
- Post-sale persistence is exposed as an authorized domain service; future work may register structured post-sale tools in the assistant registry without weakening the read-only tool boundary.
- Shipping now consumes stored product package measurements through `ShippingService.analyze_product`, and partial package data is rejected explicitly.
- Payment combinations use a documented, configurable 20% PIX default as the deterministic market-style assumption; no live market provider is required for P0.
- Fake carrier and WhatsApp adapters intentionally expose synthetic results/messages only, preserving provider isolation and privacy.
- Lexical retrieval is bounded to five passages and includes provenance; vector/embedding RAG is intentionally out of scope for this version.
- Broad exception assertions in the new coverage tests were replaced with domain-specific exceptions.

