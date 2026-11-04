---
title: 'Translate README to Brazilian Portuguese'
type: 'chore'
created: '2026-11-04'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent â€” do not modify unless human renegotiates">

## Intent

**Problem:** The project README is primarily written in English, which makes the setup, operation, observability, verification, and local development guidance less accessible to the intended Brazilian Portuguese audience.

**Approach:** Translate the README prose, headings, examples, and explanatory labels to Brazilian Portuguese while preserving commands, environment variable names, API paths, code identifiers, and technical behavior.

</frozen-after-approval>

## Implementation Notes

The change is documentation-only and is limited to `README.md`. Technical tokens and executable snippets must remain unchanged. Validate the result by checking that the README contains no remaining English instructional prose and that fenced commands are preserved.

Implementation completed: translated the README sections, setup guidance, configuration explanations, Docker instructions, verification commands, development console, simulators, and examples to Brazilian Portuguese. Technical commands and environment variable names were preserved.
