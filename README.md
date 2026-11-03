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

For local execution, `EMPORIO_DB_PATH` may point to any writable SQLite file; the default is `data/emporio.db`.

## Verification

```text
uv run pytest -q
uv run --with ruff ruff check src tests
python -m compileall -q src tests
```
