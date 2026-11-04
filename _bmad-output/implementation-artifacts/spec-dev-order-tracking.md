---
title: Local simulated order and tracking lifecycle
type: feature
created: 2026-11-04
status: done
route: dispatch
baseline_commit: f28ac7eaed4deeb11c12609be86eba5a3d8b67d7
review_loop_iteration: 0
---

<frozen-after-approval>
## Intent
Enable the approved console workflow: create a fictitious order, explicitly simulate payment and shipment, and retrieve its generated tracking through the conversation. The user approved this scope with “sim”.

## Boundaries & Constraints
Always use server-established test identities, owned orders, deterministic payment calculations, persistent audit events and conspicuous simulation labels. Only explicit console actions change order state. Keep the existing operational snapshot unchanged. Never charge, reserve stock, send real WhatsApp messages, call real Correios or expose mutation tools to the LLM.

## I/O & Edge-Case Matrix
| Scenario | Input / State | Expected behavior | Error |
|---|---|---|---|
| Create | Valid available product and test identity | Awaiting payment, unique SIM reference | Invalid input rejected |
| Dispatch early | Unpaid order | No tracking generated | Conflict |
| Paid then dispatched | Owned order | Stable fake code, Mock Correios status, simulated notification | No external effects |
| Repeated action | Same create key or transition | Idempotent result and audit | Changed creation payload conflicts |
| Other client | Foreign order/session | No private data | Authorization failure |
| Chat | Authenticated test session and SIM reference | Read-only tool result grounds response | Never invent tracking |
| Model unavailable | Verified tool facts available | Explicit partial response using verified facts | Provider failure retained |
</frozen-after-approval>

## Code Map
- `src/emporio/order_simulation.py`: isolated SQLite simulation owner; reuse payment calculator and MockCorreiosTracking.
- `src/emporio/dev_console.py`: local HTTP endpoints, test identity header and console controls.
- `src/emporio/policy_runtime.py`: runtime wiring, mandatory order lookup and verified result grounding.
- `src/emporio/tools.py`: existing read-only order_status authorization boundary.
- `src/emporio/tracing.py`: request context and persistent action traces.

## Tasks & Acceptance
- [x] Implement isolated simulation persistence and idempotent lifecycle.
- [x] Wire explicit opt-in runtime service and read-only status tool.
- [x] Add console actions and server-bound test session authentication.
- [x] Ground tracking answers only in verified current-turn tool results.
- [x] Add offline lifecycle, authorization, HTTP and browser-rendering verification.
- [x] Document configuration and test steps in README.

Given a dispatched test order, when its owner asks for tracking in the console, then the response contains its stored fake code and explicitly identifies simulation. Given the same reference without ownership, when lookup runs, then no order data is returned. Given a completed workflow, when audit is inspected after restarting the service, then state and the three lifecycle events remain available.

## Implementation Notes
Existing worktree changes are authorized ongoing work and will be preserved. No intent gaps or irreversible external actions remain. The new simulation database is separate from snapshot and session storage; freight is excluded and displayed explicitly. The approved scope requires no further approval checkpoint.

The implementation handoff could not spawn because the existing agent slots were full; implementation proceeded inline. Completed agents were then closed to enable three independent reviewers. The review diff includes previous authorized work; findings in unchanged portions of that work are recorded separately rather than expanding this feature. No version-control recording was requested; the mixed worktree is preserved without staging unrelated changes.

## Review Triage Log

| Finding | Verdict and evidence | Resolution |
|---|---|---|
| Blind 1: unauthorized lookup loops | false: ConversationService returns immediately on ToolAuthorizationError; anonymous lookup test asserts exactly one call. | Rejected |
| Blind 2: all monetary amounts become budget ceilings | medium: grounded_search_arguments applies a ceiling without comparison direction; predates this feature. | Deferred |
| Blind 3: delivery guard hardcodes deadlines/destination | medium: existing correction text is fixed despite variable evidence. | Deferred |
| Blind 4: external destination detection | medium: existing Campo Grande early return bypasses the exclusion phrase. | Deferred |
| Blind 5: evidence truncated for combined policy questions | medium: existing store/payment/return branch selects only the top passage. | Deferred |
| Blind 6: false tool flag overridden by model detection | medium: existing boolean expression permits model support to override false. | Deferred |
| Blind 7: explicit installment result excluded from quote guard | medium: existing quote parser requires maximum_installments, absent in PaymentResult. | Deferred |
| Blind 8: malformed provider data escapes error normalization | medium: telemetry reads unchecked shapes before the parsing guard. | Fixed by normalizing TypeError/AttributeError; verified tracking fallback tests cover malformed arrays, null messages and null metrics. |
| Blind 9: recovery can lose pending user message | medium: existing SessionService returns an in-memory message without persisting it in the replacement session. | Deferred |
| Blind 10: code validation permits invented delivery claims | medium: correct code alone did not validate claimed delivery. | Fixed; fabricated guaranteed arrival is rejected by regression test. |
| Edge 1: explicit installment timeout loses quote | medium: same existing PaymentResult parsing defect as Blind 7. | Deferred |
| Edge 2: installment count and amount validated independently | medium: existing validator checks membership rather than the count/amount pair. | Deferred |
| Edge 3: follow-up product without model code loses context | medium: existing history truncation removes context without injecting the selected product into the system prompt. | Deferred |
| Edge 4: fixed delivery correction | medium: same existing guard as Blind 3. | Deferred |
| Edge 5: Campo Grande exclusion unreachable | medium: same existing detection as Blind 4. | Deferred |
| Edge 6: dispatched simulation claims delivery | medium: same guard omission as Blind 10. | Fixed with delivery-claim regression. |
| Edge 7: whitespace bypasses production check | medium: environment normalization omitted strip(). | Fixed; configuration test uses padded production value. |
| Edge 8: recovery history loss | medium: same pre-existing SessionService defect as Blind 9. | Deferred |
| Edge 9: replacement session invalidates simulation binding | medium: replacement ID returned by conversation was not saved in sim_clients. | Fixed and tested across the next authenticated message. |
| Edge 10: pending response overwrites new client session | medium: old HTTP callback updated the active session after client switching. | Fixed with request token/session guards; browser regression invokes both flows. |
| Edge 11: malformed telemetry breaks verified fallback | medium: same provider normalization defect as Blind 8. | Fixed and tested through ConversationService. |
| Edge 12: numeric catalog name errors before schema validation | medium: existing argument rewriting invokes regex on unvalidated values. | Deferred |
| Edge 13: oversized product ID overflows SQLite | low: input lacked the signed 64-bit upper bound. | Fixed and tested. |
| Edge 14: older than 30 orders disappear from panel | low: bounded recent listing is intentional for this local test panel; API references and stored records remain valid. | Pagination deferred as optional evolution; recent limit documented. |
| Edge 15: diagnostic capture bypassed by planned payment | low: existing diagnosis script expects delegate invocation on the first round. | Deferred |
| Edge 16: catalog limit schema removed | medium: earlier work removed the limit parameter; current simulation adds no catalog schema changes. | Deferred |
| Verification 1: outgoing tool arguments lack wire assertion | medium: existing fake endpoint accepted either serialized representation. | Added object-value assertion to the provider contract test. |
| Verification 2: browser authentication path untested | medium: previous DOM harness discarded event handlers. | Harness now invokes start/create/chat and checks token headers, session binding and displayed response. |
| Verification 3: expired simulation token untested | medium: previous ownership cases used fresh tokens. | HTTP test expires credentials and verifies 403 for reads, actions and chat with unchanged order state. |

## Verification
Run focused simulation and existing console/tracking tests, then the complete offline pytest suite with a workspace-local temporary directory. Exercise the embedded JavaScript with the existing Node DOM harness.

The full offline suite passed with one opt-in live-provider test skipped. Subsequent focused verification passed: 37 passed / 1 skipped before the final review patches, then 29 passed covering session replacement, browser identity changes, lifecycle, HTTP, trace audit and tracking guards. Final provider-malformation, lifecycle and serializer regression checks passed: 26 passed / 1 skipped. No real carrier, payment or WhatsApp requests are required. Review findings affecting this feature were fixed; earlier payment/catalog/session/delivery limitations and optional simulation-history pagination were recorded in deferred-work.md.
