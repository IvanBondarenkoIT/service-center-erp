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

EXPOSE 8035

# Railway sets PORT at runtime (often 8080). Do not ENV PORT here — it can pin 8035.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8035}"]
