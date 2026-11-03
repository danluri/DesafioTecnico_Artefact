# Empório da Música

The offline P0 application uses SQLite and requires no external credentials. The session boundary is available through `SessionService` and stores only normalized, bounded message envelopes.

## Docker

Run `docker compose up --build`. This is a storage-ready P0 container: it initializes SQLite at `/data/emporio.db`, reports `READY`, and remains running with the named `emporio-data` volume mounted. There is no HTTP service yet. The default principal-binding HMAC secret is development-only; set `EMPORIO_PRINCIPAL_HMAC_SECRET` to an explicit deployment secret.

For local execution, `EMPORIO_DB_PATH` may point to any writable SQLite file; the default is `data/emporio.db`.

## Verification

```text
uv run pytest -q
uv run --with ruff ruff check src tests
python -m compileall -q src tests
```
