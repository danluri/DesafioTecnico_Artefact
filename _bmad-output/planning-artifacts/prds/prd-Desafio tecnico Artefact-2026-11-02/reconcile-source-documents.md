# Source Reconciliation — Existing Project Package

## Inputs reviewed

`PROJECT_BRIEF.md`, `PRD.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`, `ROADMAP.md`, `TEST_STRATEGY.md`, `BMAD_HANDOFF.md`, and the four ADRs under `docs/adr/`.

## Reconciled strengths

- All inputs agree that structured data is the source of truth for exact operational facts.
- All inputs agree that policy retrieval needs section/page provenance.
- Authorization and privacy are treated as server-side controls, not prompt instructions.
- P0 and optional P1 capabilities are consistently separated in the refined PRD.
- The proposed test matrix supplies concrete negative cases for authorization, injection, provider failure, and unavailable data.

## Gaps carried into the refined PRD

1. The documents describe a planned system; no implementation or executed test evidence was supplied.
2. The workspace root and the architecture-package directory are not yet reconciled as a single implementation root.
3. Publication permission for customer PII and the internal policy PDF is not established.
4. Shipping at exactly R$500, installment minimums, conflicting contact data, and snapshot date remain unresolved.
5. The real LLM provider for the demonstration is not selected.
6. The original roadmap contains implementation details; those were retained in `addendum.md` and not treated as product requirements.

## Disposition

The refined PRD preserves these gaps as open questions or explicit assumptions. It does not claim that any proposed architecture, metric, integration, test, or conversation has already been implemented or verified.
