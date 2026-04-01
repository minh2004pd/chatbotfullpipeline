FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files (cả uv.lock để build deterministic)
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev group, --frozen đảm bảo dùng đúng lockfile)
RUN uv sync --no-dev --no-cache --frozen

# Copy source
COPY app/ ./app/

# Create uploads and logs directory
RUN mkdir -p /app/uploads /app/logs

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
