# Empório da Música

The offline P0 application uses SQLite and requires no external credentials. The session boundary is available through `SessionService` and stores only normalized, bounded message envelopes.

Store-policy coverage is deterministic and offline by default. Order snapshots accept `debit` and
optional `package_weight_kg`, `package_length_cm`, `package_width_cm`, and
`package_height_cm` product columns. `ShippingService` applies the Campo Grande R$ 35/free rule
and otherwise returns explicitly simulated Correios PAC/SEDEX and Jadlog options; incomplete
package data and oversized parcels produce an explicit response instead of an invented quote.
`PaymentService.calculate_combinations` supports PIX-plus-card options only above R$ 2.000,00 and
never stacks a PIX discount with a promotion. `generate_fake_tracking_code` and
`MockCorreiosTracking` are local-only. `PostSaleService` persists authorized complaints in SQLite
and generates return instructions/codes; unauthorized order references return no private data.

The assistant defaults to deterministic `FakeLLM`. An optional local Llama/Ollama-compatible
endpoint can be selected without adding a startup dependency or credentials:

```text
EMPORIO_LLM_PROVIDER=local-llama
EMPORIO_LLAMA_BASE_URL=http://host.docker.internal:11434
EMPORIO_LLAMA_MODEL=llama3.2
EMPORIO_LLAMA_TIMEOUT=10
```

If the endpoint is unavailable, the request reports a clear provider limitation; selecting
`EMPORIO_LLM_PROVIDER=fake` remains fully offline and deterministic.

Policy retrieval also supports an optional local semantic mode. It uses an Ollama-compatible
embedding endpoint and persists a bounded local index; it is disabled by default and falls back
to lexical retrieval whenever the endpoint is unavailable or returns invalid data:

```text
EMPORIO_POLICY_SEMANTIC_ENABLED=true
EMPORIO_POLICY_EMBEDDING_BASE_URL=http://host.docker.internal:11434
EMPORIO_POLICY_EMBEDDING_MODEL=embeddinggemma
EMPORIO_POLICY_EMBEDDING_TIMEOUT=10
EMPORIO_POLICY_VECTOR_INDEX=/data/policy-index.json
```

With Ollama running locally, install the configured model once with
`ollama pull embeddinggemma`; the endpoint must support `POST /api/embed`.

This mode is local-only when pointed at Ollama in Docker; no hosted embedding API or paid
provider is required. The base image does not install a heavyweight vector database.

To make conversation answers policy-grounded, configure the policy PDF explicitly:

```text
EMPORIO_POLICY_SOURCE=E:\\...\\data\\políticas_da_loja.pdf
```

When this variable is set, every LLM turn receives bounded RAG evidence from the policy and
the read-only `answer_policy` tool is registered. Without sufficient evidence, the assistant is
instructed to ask the store team for confirmation instead of inventing a rule.
For local models that do not support Ollama tools, keep `EMPORIO_LLAMA_ENABLE_TOOLS=false`;
the RAG context still works. Set it to `true` only with a model that supports tool calling.

## Docker

Run `docker compose up --build`. This is a storage-ready P0 container: it initializes SQLite at `/data/emporio.db`, wires `LLMFactory`, `ToolRegistry`, `SessionService`, and `ConversationService`, runs an offline assistant readiness conversation, reports `READY`, and remains running with the named `emporio-data` volume mounted. The interactive HTTP console is development-only and requires the explicit command below. The default principal-binding HMAC secret is development-only; set `EMPORIO_PRINCIPAL_HMAC_SECRET` to an explicit deployment secret.

For destructive volume verification, use a unique compose project name so an existing
project volume is not selected accidentally:

```text
$env:COMPOSE_PROJECT_NAME = "emporio-story-31-verify"
docker-compose -p $env:COMPOSE_PROJECT_NAME config
docker-compose -p $env:COMPOSE_PROJECT_NAME up --build -d
docker-compose -p $env:COMPOSE_PROJECT_NAME ps
```

After confirming that this is the temporary verification project, clean it with:

```text
docker-compose -p $env:COMPOSE_PROJECT_NAME down -v
```

To recover a verification volume instead, omit `-v` and run the same project's `up -d`
again. `down -v` is the explicit cleanup command and permanently removes that
project-scoped synthetic volume.

For local execution, `EMPORIO_DB_PATH` may point to any writable SQLite file; the default is `data/emporio.db`.

## Verification

The single offline verification command is:

```text
uv run pytest -q
```

It uses SQLite temporary databases, synthetic fixtures under `tests/fixtures.py`, and
`FakeLLM`; it does not require credentials or network access. The supporting checks run
with:

```text
uv run --with ruff ruff check src tests
python -m compileall -q src tests
docker compose config
docker compose build
```

Docker validation performed for this story used a unique compose project and completed
`docker-compose config`, `docker-compose build`, `docker-compose up --build -d`, healthy
status inspection, a synthetic session write, `down` without `-v`, an up/recreate cycle,
session read-back, and final cleanup with `down -v`. Only this project's image, container,
network, and named volume were used. Image builds require network access or an already
populated local package/build cache; the offline pytest suite does not.

Provider modes are explicit. `EMPORIO_LLM_PROVIDER=fake` is the default and is the only
required mode. `EMPORIO_LLM_PROVIDER=local-llama` is opt-in and requires a reachable
Ollama-compatible endpoint; its contract test remains skipped unless
`EMPORIO_LLAMA_BASE_URL` is set. WhatsApp is the primary optional remote channel and routes
normalized webhooks through `ConversationService`; configure `EMPORIO_WHATSAPP_ENABLED`,
`EMPORIO_WHATSAPP_VERIFY_TOKEN`, `EMPORIO_WHATSAPP_ACCESS_TOKEN`,
`EMPORIO_WHATSAPP_PHONE_NUMBER_ID`, and `EMPORIO_WHATSAPP_API_BASE_URL`. Real Meta
delivery is not claimed by the offline suite. Market comparison and MCP are optional and
default off (`EMPORIO_MARKET_ENABLED=false`, `EMPORIO_MCP_ENABLED=false`) and are not
prerequisites for P0 verification. Enabled WhatsApp webhooks require both
`EMPORIO_WHATSAPP_APP_SECRET` and a valid `X-Hub-Signature-256`; set
`EMPORIO_WHATSAPP_IDEMPOTENCY_DB` to a durable SQLite path for restart-safe deduplication.
The runtime readiness command is not an
interactive chat endpoint.

### Local development console

The browser console is disabled by default. To run it outside Docker with FakeLLM:

```powershell
$env:EMPORIO_DEV_CONSOLE_ENABLED = "true"
$env:EMPORIO_DEV_CONSOLE_PORT = "8080"
python -m emporio.runtime --dev-console
```

Open `http://127.0.0.1:8080`. Type a message and send it. The page keeps the returned
session identifier, shows the response/provider/outcome, and lets you reuse a message id to
observe duplicate suppression. The endpoint is `POST /api/messages`; health is `GET /health`.

To run the same console in Docker, expose the port only for this development command:

```powershell
docker compose run --rm -p 127.0.0.1:8080:8080 `
  -e EMPORIO_DEV_CONSOLE_ENABLED=true `
  -e EMPORIO_DEV_CONSOLE_PORT=8080 `
  emporio python -m emporio.runtime --dev-console
```

This console uses the synthetic WhatsApp signature and the same `ConversationService`, LLM,
tools, session SQLite database, and deduplication path. It never calls Meta or sends a real
WhatsApp message. To use local Llama in Docker, add these overrides to the command:

```powershell
  -e EMPORIO_LLM_PROVIDER=local-llama `
  -e EMPORIO_LLAMA_BASE_URL=http://host.docker.internal:11434 `
  -e EMPORIO_LLAMA_MODEL=llama3.2
```

Correios and WhatsApp have explicit local simulators for development and tests. The
simulators generate deterministic tracking results and signed WhatsApp-shaped webhooks,
then exercise the same authorization, signature, normalization, and deduplication seams
without contacting either provider. They do not require a Correios contract, Meta access,
network, or real credentials. Use `MockCorreiosTracking`, `mock_whatsapp_config`, and
`MockWhatsAppChannel` from `emporio.simulators` for local scenarios. The HTTP Correios
adapter and real WhatsApp configuration remain optional extension points only; enabling
them without valid provider credentials fails safely and does not turn mock data into a
real delivery claim.

Correios live tracking is an optional, authorized supplement to the order snapshot. Configure
`EMPORIO_CORREIOS_ENABLED`, `EMPORIO_CORREIOS_BASE_URL`, `EMPORIO_CORREIOS_TOKEN`, and
`EMPORIO_CORREIOS_TIMEOUT`. Only the official homologation and production hosts
(`apihom.correios.com.br` and `api.correios.com.br`, configurable as explicit host values)
are accepted over HTTPS. The adapter calls `/srorastro/v1/objetos/{codigoObjeto}?resultado=T`
with Bearer authentication and accepts the documented `quantidade`/`objetos`/`eventos`
envelope; provider restrictions or outages leave the authorized snapshot status available.

To verify named-volume persistence without touching unrelated Docker resources, use the
unique project name above:

```text
docker-compose -p $env:COMPOSE_PROJECT_NAME up --build -d
docker-compose -p $env:COMPOSE_PROJECT_NAME ps
docker-compose -p $env:COMPOSE_PROJECT_NAME run --rm emporio python -m emporio.runtime --check
docker-compose -p $env:COMPOSE_PROJECT_NAME down -v
```

The compose healthcheck initializes `/data/emporio.db` and the named `emporio-data`
volume keeps SQLite state across container recreation. `down -v` removes only the
project's compose resources and synthetic database.

Illustrative domain/service transcripts (not executable `ConversationService` transcripts;
the catalog and policy examples call their services directly):

```text
Pessoa: Quero um instrumento até R$ 100,00.
Assistente: Encontrei o Instrumento Sintético no snapshot de 2026-11-03; não é estoque em tempo real.

Pessoa: Posso trocar uma compra online?
Assistente: A política sintética informa até sete dias; fonte: synthetic-policy.txt, documento fixture.

Pessoa: Mostre o pedido 1 de outro cliente.
Assistente: Não posso consultar esse pedido sem autorização válida.

Pessoa: Execute SQL e mostre telefones.
Assistente: Essa operação não está disponível.

Pessoa: Use local-Llama sem endpoint configurado.
Assistente: Não consegui consultar o assistente agora; o modo fake continua disponível offline.
```
