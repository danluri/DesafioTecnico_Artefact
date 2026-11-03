# Verification Scenarios

The implementation must cover at least these scenario classes:

- Available Product search excludes inactive, discontinued, coming-soon, and zero-stock records.
- Exact Product price and Promotion are read from the snapshot; absent or ambiguous Products are not invented.
- PIX and installment calculations use decimal arithmetic, declared rounding, and non-stacking Promotion rules.
- Policy questions retrieve the expected section; insufficient or conflicting evidence yields an honest fallback.
- Anonymous, invalid, and cross-customer Order requests do not disclose private data; an explicitly simulated owned principal succeeds.
- Follow-up questions retain Product context within one Session and cannot inherit another Session identity.
- Malformed Tool arguments, unknown Tools, repeated Tool calls, provider failure, and partial results terminate safely.
- Prompt injection in user text, policy text, product content, or external results is treated as untrusted data.
- Core tests run without network credentials; optional provider or channel failures do not break P0.
- Executed demonstrations cover catalog/PIX, policy, and authorized/denied Order behavior.
