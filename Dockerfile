FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV EMPORIO_DB_PATH=/data/emporio.db
ENV EMPORIO_LLM_PROVIDER=fake
ENV EMPORIO_DEV_CONSOLE_ENABLED=false
# Optional override at runtime: EMPORIO_LLM_PROVIDER=local-llama and
# EMPORIO_LLAMA_BASE_URL=http://host.docker.internal:11434
RUN mkdir -p /data
VOLUME ["/data"]

CMD ["python", "-m", "emporio.runtime"]

