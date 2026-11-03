---
title: 'Generate mock data for Correios credential-ready tests'
type: 'chore'
created: '2026-11-03'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** The Correios adapter is prepared for real credentials, but its automated coverage should prove the integration contract without making live requests or requiring secrets.

**Approach:** Add deterministic test data builders that generate official-shaped Correios Rastro payloads and use them in mocked success, failure, and configuration tests, while retaining the existing authorization and snapshot-fallback coverage. Keep all real credentials and provider calls opt-in through environment configuration.

</frozen-after-approval>

## Implementation Notes

- Added a deterministic `correios_payload` factory and `MockCorreiosResponse` fixture in `tests/test_integrations.py`.
- Covered environment-only credential loading, official-shaped success normalization, Bearer/query construction, mocked HTTP and transport failures, wrong content type, disabled/missing credential no-provider-call behavior, and the existing authorization boundary/fallback.
- No production credentials, live endpoint calls, or changes inside the approved intent block were introduced.

## Verification

**Commands:**
- `python -m pytest -q` -- passed: 111 tests passed, 1 skipped.
- `uv run --with ruff ruff check src tests` -- passed: all checks passed.
- `python -m compileall -q src tests` -- passed: compilation succeeded.

## Review Triage Log

- fixed -- Added mocked transport exceptions, wrong content type, and disabled-provider coverage.
- fixed -- The missing-token test already asserted the provider was not called; the disabled configuration now has the same assertion.
- false -- Existing tests already cover inconsistent quantity, divergent code, and malformed payloads; the valid-data factory intentionally stays focused on constructing normal official-shaped responses.
- fixed -- Clarified that authorization and snapshot fallback were existing coverage retained by this change, not newly implemented behavior.
- fixed -- Recorded the actual verification result: 111 passed and 1 skipped, plus lint and compilation success.
- fixed -- Replaced the corrupted dash in the spec with ASCII text.

