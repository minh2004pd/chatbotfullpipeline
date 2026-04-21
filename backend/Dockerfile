FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN useradd -m -d /home/appuser appuser

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --no-dev --no-cache --locked

COPY app/ ./app/

RUN mkdir -p /app/uploads /app/logs /app/wiki && \
    chown appuser:appuser /app/uploads /app/logs /app/wiki

ENV HOME=/home/appuser
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
