FROM ghcr.io/astral-sh/uv:0.8.14 AS uv

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev && \
    useradd --create-home --uid 10001 appuser && \
    chown -R appuser:appuser /app

USER appuser
EXPOSE 8123

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8123/healthz', timeout=4)"]

CMD ["uvicorn", "extto_torznab.app:app", "--host", "0.0.0.0", "--port", "8123"]
