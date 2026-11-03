---
title: 'Simulate Correios and WhatsApp integrations locally'
type: 'feature'
created: '2026-11-03'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** The project cannot use live Correios tracking because there is no Correios contract, and it cannot deliver through WhatsApp because Meta API access is unavailable. The application still needs a credible local simulation for development and demonstrations.

**Approach:** Add deterministic in-process simulators that implement the existing Correios tracking port and exercise the signed WhatsApp webhook adapter with generated payloads. Make the simulation require no external credentials, network, contract, or provider claim, while preserving the real adapters as future extension points.

**Always:** Mark simulated responses as mock/local data, keep authorization and deduplication behavior active, and keep real provider credentials optional and out of source control.

**Never:** Call Correios or Meta from the simulator, imply that a simulated delivery was real, or weaken webhook signature and order-ownership checks in the real adapters.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| MOCK_CORREIOS | Authorized tracking lookup with a valid synthetic code | Deterministic `TrackingResult` with mock source/provenance | Invalid code returns the same safe unavailable path |
| MOCK_WHATSAPP | Generated local message delivered through the webhook adapter | Conversation receives one normalized message | Re-delivery is marked duplicate and does not call the conversation twice |
| NO_CREDENTIALS | Simulator initialized with no provider secrets | Simulation works offline | Real adapters remain disabled or unavailable |

</frozen-after-approval>

## Implementation Notes

- Added `src/emporio/simulators.py` with a deterministic Correios provider and a local WhatsApp channel that signs generated payloads with a synthetic secret.
- The WhatsApp simulator rejects provider credentials, validates generated fields, and still uses the real webhook adapter for signature, normalization, and deduplication behavior.
- Added tests for network-free Correios authorization, mock WhatsApp restart-safe idempotency, credential rejection, and invalid generated fields.
- The simulator is explicit test/development infrastructure; runtime provider wiring remains opt-in and no live request is made.

## Verification

**Commands:**
- `python -m pytest -q` -- passed: 117 tests passed, 1 skipped.
- `uv run --with ruff ruff check src tests` -- passed: all checks passed.
- `python -m compileall -q src tests` -- passed: compilation succeeded.

## Review Triage Log

- fixed -- Replaced corrupted simulator text with Unicode escape sequences and ASCII-safe message text.
- fixed -- Clarified that simulators are explicit development/test tools, not automatically wired runtime providers.
- fixed -- `MockWhatsAppChannel` now accepts only the synthetic mock configuration and rejects provider credentials.
- fixed -- Added an explicit `urlopen` guard proving the Correios simulation is network-free.
- fixed -- Added SQLite-backed mock WhatsApp deduplication coverage across adapter recreation.
- fixed -- Connected `MockCorreiosTracking` to `AuthorizedCorreiosTrackingService` and verified unauthorized lookup remains hidden.
- fixed -- Mock WhatsApp payload fields are validated before generation.
- false -- `TrackingResult` intentionally omits the tracking code to avoid exposing private identifiers; the authorized service verifies ownership before invoking the simulator.
- fixed -- Marked the spec done and recorded implementation and verification evidence.

