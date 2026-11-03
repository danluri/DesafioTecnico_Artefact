# Empório da Música

The offline P0 application uses SQLite and requires no external credentials. The session boundary is available through `SessionService` and stores only normalized, bounded message envelopes.

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

## Docker

Run `docker compose up --build`. This is a storage-ready P0 container: it initializes SQLite at `/data/emporio.db`, wires `LLMFactory`, `ToolRegistry`, `SessionService`, and `ConversationService`, runs an offline assistant readiness conversation, reports `READY`, and remains running with the named `emporio-data` volume mounted. There is no HTTP or CLI conversation endpoint yet: the readiness conversation proves wiring and storage only; it is not an interactive assistant interface. The default principal-binding HMAC secret is development-only; set `EMPORIO_PRINCIPAL_HMAC_SECRET` to an explicit deployment secret.

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
`EMPORIO_LLAMA_BASE_URL` is set. WhatsApp, market comparison, and MCP are optional and
are not prerequisites for P0 verification. The runtime readiness command is not an
interactive chat endpoint.

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
