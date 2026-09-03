FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY templates ./templates
COPY static ./static
COPY scripts ./scripts
COPY alembic.ini .
COPY alembic ./alembic

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Do not EXPOSE a fixed local port: Railway may route the public domain there
# while uvicorn listens on $PORT (often 8080).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8035}"]
