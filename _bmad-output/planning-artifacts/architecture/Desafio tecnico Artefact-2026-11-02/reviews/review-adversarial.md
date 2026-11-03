# Adversarial Architecture Review

## Verdict

No incompatible pair was found that can obey every stated AD and still disagree on a P0 invariant. The most important collision risks are explicitly closed by AD-1, AD-3, AD-6, AD-7, AD-8, and AD-9.

## Pair checks

1. **CLI versus HTTP:** both must call ConversationService and normalized message contracts; channel rules cannot diverge.
2. **SQLite repository versus policy index:** AD-4 separates operational and policy retrieval while AD-9 assigns the persistence boundary.
3. **LLM provider versus FakeLLM:** AD-5 requires the same normalized port, capabilities, and contract tests.
4. **Tool adapter versus Order service:** AD-6 and AD-7 require schema validation and server-side ownership checks in the use case.
5. **MCP versus local tools:** AD-8 and AD-10 require reuse of the same use cases and prohibit duplicated rules.
6. **Market service versus official catalog:** AD-3 and AD-10 keep External Offers separate from Product price state.
7. **Session storage versus channel identity:** AD-8 and the identity convention require normalized message contracts and isolated session state.
8. **Ingestion versus customer-facing repositories:** AD-3 and AD-9 require atomic ingestion and a single snapshot owner.

No new invariant is required by these checks.
