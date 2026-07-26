FROM python:3.13-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source + migration config
COPY backend/ .
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic

# Create data dir for SQLite (fallback when Postgres not configured)
RUN mkdir -p /app/data

# Railway injects PORT env var — use it, default to 8000 for local dev
ENV HOST=0.0.0.0
ENV PORT=8000
ENV DATABASE_URL=sqlite+aiosqlite:///./data/swiftgate.db

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=20s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", \"8000\")}/health')" || exit 1

# Run migrations then start server (Railway overrides PORT)
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
