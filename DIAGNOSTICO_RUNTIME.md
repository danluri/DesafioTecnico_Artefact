# Runtime diagnosis — 2026-11-04

The original system prompt was retained unchanged during the measurements.

## Confirmed findings

1. SQLite connections previously used the default thread restriction. HTTP handlers and tool workers run on different threads from the connection creator. A minimal reproduction raises `sqlite3.ProgrammingError`. Connections now allow cross-thread access and complete repository operations are serialized with a reentrant lock. The HTTP/tool integration test verifies persistence and successful tool execution.
2. `data/catalog.db` existed without an ingested operational snapshot. A direct catalog search raised `CatalogNotFoundError: no operational snapshot has been ingested`. The supplied CSVs were imported on this run. A category search for `Violões`, with budget 1000, returns 12 available products.
3. A cold direct Ollama call with the original prompt (7402 characters, 2133 evaluated tokens) took 171.527 seconds. Ollama reported load duration 20.688 s, prompt evaluation 139.160 s, and generation 11.369 s. Server logs show 9/33 layers on GPU and about 16–18 prompt tokens/s. The previous runtime log independently records a 180.118 s timeout. Cold inference is close to the application timeout; the exact cause of the earlier timing difference was not measured.
4. After warming the model, the real runtime completed in 42.831 seconds, with outcome `success`, one tool call and `persisted` storage. This demonstrates successful execution, not answer correctness.
5. The completed runtime returned a false negative. The persisted tool result records criteria `name=violão`, `category=violão`, budget 1000, and zero products. Search combines name and category filters with AND; model names do not contain the generic word `violão`. Separate controlled searches returned 12 results for category `Violões`, zero for unaccented `violoes`, and zero for product name `violões`. Search interpretation and normalization still need correction; absence of matching rows is currently presented as absence of inventory.

## Evidence and reproduction

- Application log: `data/emporio-runtime.log`.
- Ollama server log: `%LOCALAPPDATA%/Ollama/server.log`.
- Synthetic real-runtime history: `data/diagnostic-session.db`.
- Manual diagnostic: `PYTHONPATH=src python tests/diagnose_local_runtime.py`.
- Query comparisons: add `--catalog-variants`.
- Saved diagnostic tool results: add `--history`.

The manual full diagnostic uses the supplied local PDF and catalog, sends one streaming request to measure first output and provider metrics, then executes the real runtime with an isolated session database. It does not modify the system prompt. Running it requires Ollama and can take several minutes.

## Outstanding work

- Instrument/category search normalization is implemented: standalone guitar instrument terms become category filters, while specific model names remain name filters. Regression tests cover accents, singular/plural, budget, stock and nonexistent models.
- Choose an inference latency strategy while preserving the original prompt. Increasing the timeout alone does not improve cold inference throughput.
- The first real HTTP run after search correction successfully executed the tool and returned 12 matching products, but its second Ollama call timed out. Ollama logged input truncation from 4290 to 2050 tokens. Search tool output is now compact (IDs, names, prices, stock, category and one snapshot timestamp), and generation is bounded through `EMPORIO_LLAMA_MAX_TOKENS=512`, preserving the original prompt. The new second-call input measured 2601 tokens without that truncation.

## Final HTTP verification after search and payload corrections

The real HTTP console completed with `outcome=success`, `tool_calls=1`, `persistence=persisted` and `provider_error=null`. Its response listed the 10 products on the first page, with prices matching the imported snapshot. There are 12 matching products in total. Total wall time was 247.749 s, including an initial request that spent time waiting for the prior diagnostic inference. The successful second call used the compact tool output. The original system prompt was unchanged.

Residual response-quality issue: the model incorrectly described the R$999.00 item as above R$1000.00, even though the returned prices and deterministic budget filter were correct. This is a generation error; the search correction does not guarantee that all generated commentary is accurate.

## Store-information routing and compact prompt verification

After authorization to change the prompt while preserving its essence, the prompt
was condensed while retaining persona, tool/RAG grounding, privacy, applicability
conditions and no-invention rules. Address and return queries now use the manual;
unknown non-product questions also attempt retrieval. Independent store-information
questions do not resend unrelated catalog history. Policy evidence diagnostics now
reflect retrieved passages instead of treating fallback text as evidence.

Real HTTP console tests with Ollama `llama3.1:latest`:

| Question | Verified outcome | Observed total time |
|---|---|---|
| Store address | Address from page 2, success, persisted | 67.3 s |
| Takamine GD20 price | R$2199.00 and 5 units, matching snapshot, success, persisted | 50.2 s |
| Guitars up to R$1000 | 12 matches, 10 rows, three correctly priced examples in generated summary, success, persisted | 134.9 s |
| Return after changing one's mind | Retrieved return conditions, seven-day receipt window and follow-up about receipt date, success, persisted | 54.1 s |

The return model response omitted the online-purchase qualification. A deterministic
guard now preserves that condition if it is explicitly in the retrieved text but
missing from the generated response; its omission scenario is covered by a test.
The four observed executions completed without provider errors; future latency and
response wording remain model-dependent. Additional route tests cover address/CEP
synonyms, opening hours, contacts, warranty, privacy, shipping, and mixed product/PIX
queries. Broad end-to-end coverage of all possible customer questions is not claimed.

## Shelby payment regression — trace 2f71f9d0-da4d-42ef-81a2-f6bec56c93cd

The failing request advertised zero tools, retained 12 history messages and sent
8218 characters to Ollama. The router did not recognize Shelby/SN-100 as a product.
The provider timed out at 180 seconds. Reproduction also exposed an invented
category filter and model output that ignored a calculation tool when merely offered.

Named-model payment requests now plan read-only catalog lookup and calculation
before one final LLM completion. Exact quote amounts and eligible plans are validated
against calculator output. A regression test includes 12 old messages and verifies
that they are omitted while current tool-call pairs are retained. Another discovered
calculator bug applied the R$100 minimum to valid 4–6 installment plans; the range
checks are now mutually exclusive, matching the R$80 minimum for that range.

Verified snapshot values for product 89: R$549.00; PIX R$521.55; eligible maximum
6 installments of R$91.50. A real HTTP test deliberately used a 1-second Ollama
timeout and returned these verified conditions in 5.6 seconds, with 2 successful
tool calls, persisted storage, `outcome=partial` and `provider_error=TimeoutError`.
This tests failure recovery honestly: cold inference latency remains, and successful
LLM prose generation is not claimed for that run. Recovery applies only after a
successful verified payment quote, not to arbitrary failed queries.

## PIX intent plus tracking — trace aa050584-1bc2-4149-96f9-52b5afda96f7

The provider returned normally (16 generated tokens) but its text was the generic
infrastructure-failure placeholder. The application incorrectly counted this as
success. Routing retrieved payment policy page 3 instead of tracking page 5 and
retained seven history messages. Tracking now has retrieval priority; independent
tracking clarification excludes unrelated history and old failure placeholders.
Known generated infrastructure-error placeholders are classified as `answer_failure`
instead of success when not recovered by an intent-specific guard.

A real HTTP reproduction with long history retrieved page 5, sent only the current
turn, and returned an order-number clarification without provider errors in 119.9 s.
Additional guard tests enforce dispatch/identity-validation prerequisites, reject
invented tracking codes and unverified payment/shipment claims, and recover safely
from provider timeouts. Such recovery is marked partial. This does not implement a
checkout/payment confirmation or a new order; no tracking code is generated from
the customer's statement of payment intent.

## Payment follow-up — trace cc80ef2c-78ca-4caf-9e94-e4ecb55bcb8b

The phrase "Quais as condições de pagamento desse produto?" did not match the old
prefix-only follow-up detector. It fell back to an LLM search call containing
unsupported fields (`availability_only`, `limit`, `offset`) and failed validation.
The resolver now recognizes referential expressions anywhere in the question,
prefers a unique persisted catalog result from that session and performs a fresh
lookup/payment calculation. Multiple or missing selections ask for clarification.

Regression tests cover the two turns, a recreated session service/LLM between turns,
PIX/parcelamento variants, ambiguous lists and isolation from other sessions.
A real two-request HTTP test used the same returned session ID:
first price lookup returned product 89 (Shelby, R$549.00); the follow-up completed
in 94.8 seconds with `success`, two planned tools, `persisted` storage and no
provider error. Its answer quoted R$549.00, PIX R$521.55 and up to six installments
of R$91.50. Total test time including the first cold price request was 230 seconds.
The resolved context is recorded as `product_reference_resolved` in the trace.
