---
title: 'Replace Empório da Música system prompt'
type: 'feature'
created: '2026-11-03'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent â€” do not modify unless human renegotiates">

## Intent

**Problem:** The assistant's current policy-grounding prompt is shorter than the approved Empório da Música service guidance and does not express the full persona, operational-source rules, privacy constraints, response flow, and evidence-handling requirements.

**Approach:** Replace the prompt assembled by `_grounding_prompt` with the user-provided system prompt while retaining runtime interpolation of the retrieved policy evidence at the `{evidence}` placeholder.

</frozen-after-approval>

## Implementation Notes

The change is limited to the prompt construction in `src/emporio/policy_runtime.py`. Existing evidence retrieval, message ordering, delivery validation, tool authorization, and provider behavior remain unchanged. Verify with the focused policy-runtime tests and the full test suite if available.

Implementation completed: replaced the previous compact grounding text with the supplied nine-section system prompt and retained dynamic evidence injection.
