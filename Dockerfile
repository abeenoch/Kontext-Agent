FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# System deps kept minimal for smaller image and faster build.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    libpq5 \
    curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data ./data

# Non-root runtime user for safety.
RUN adduser --disabled-password --gecos "" appuser \
 && chown -R appuser:appuser /app
USER appuser

ENV CHROMA_DIR=/app/chroma_db \
    TRANSCRIPTS_DIR=/app/data/meeting_transcripts

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
