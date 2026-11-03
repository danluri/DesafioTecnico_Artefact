FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV EMPORIO_DB_PATH=/data/emporio.db
RUN mkdir -p /data
VOLUME ["/data"]

CMD ["python", "-m", "emporio.runtime"]

