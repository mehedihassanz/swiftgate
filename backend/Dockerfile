FROM python:3.13-slim

WORKDIR /app

# Copy only backend requirements first (for layer caching)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code only
COPY backend/ .

# Create data directory for SQLite
RUN mkdir -p /app/data

ENV DATABASE_URL=sqlite+aiosqlite:///./data/swiftgate.db
ENV HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
