# Kontext Agent

Full-stack meeting and knowledge assistant with real-time transcription, periodic and final summaries, RAG search, and voice/chat.

## What's Inside
- **Backend:** FastAPI (`app/`), Postgres for auth/chat/meeting data (transcripts and summaries encrypted at rest), ChromaDB (`chroma_db/`) for vectors.
- **LLM:** Groq or Ollama chat completions with configurable model and temperature; PII is scrubbed before prompts.
- **Telemetry:** OpenTelemetry traces for every LLM call plus Prometheus metrics for latency, TTFT, throughput, errors, and estimated cost.
- **Speech:** Deepgram STT (meetings and voice chat) and TTS.
- **Frontend:** React 19 + Vite + Tailwind (`frontend/`).
- **Integrations:** SMTP email, Notion export, JWT auth with signup/login/reset, rate limiting, meeting delete, and retention/TTL.

## Core Features
- **Live meeting WebSocket** (`/meeting/ws`): PCM16 audio (binary or base64), interim/final transcripts, keep-alive plus auto reconnect, `STOP` triggers a structured final summary, runtime reconfig via `{"type":"config","sample_rate":16000}`.
- **Summaries:** Periodic delta-based snapshots (last N minutes) plus final Markdown summary; fallback summary if the LLM fails.
- **Post-meeting chat** (`POST /meeting/{id|recent|any|latest}/chat`): RAG over the meeting and cross-meeting context; accepts voice input; commands to email or Notion-export the summary.
- **Document chat** (`POST /docs/chat`): PDF/TXT upload (50 MB) with ingestion jobs, per-tab collections, optional RAG bypass, voice input.
- **General chat** (`POST /chat/query`): Remembers recent history and uses doc context when available; optional voice input.
- **Voice chat socket** (`/voice-chat/ws`): Real-time STT -> LLM -> TTS with conversation recall.
- **Data hygiene:** PII redaction before LLM calls, encrypted DB columns for transcripts/summaries, meeting retention/TTL, and hard delete.

## Environment
Copy `.env.example` to `.env` and set at least:
- `DATABASE_URL` (async SQLAlchemy URI; Postgres via `asyncpg` recommended)
- `GROQ_API_KEY`
- `DEEPGRAM_API_KEY`
- `JWT_SECRET` (>=32 chars in production)
- `ENCRYPTION_KEY` (falls back to `JWT_SECRET`, but set a dedicated key for production)
- `PRELOAD_EMBEDDINGS` (set to `true` to download the embedding model at startup; defaults to `false` to speed container health checks)

Common optional keys:
- `LLM_PROVIDER` (`groq` or `ollama`), `GROQ_MODEL`, `OLLAMA_MODEL`
- `LLM_TEMPERATURE`, `LLM_TIMEOUT`, `OLLAMA_TIMEOUT`, `OLLAMA_KEEP_ALIVE`
- `OTEL_SERVICE_NAME`, `OTEL_TRACES_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`

- `EMBEDDING_MODEL` (defaults to `all-MiniLM-L6-v2`)
- `CHROMA_DIR`
- `MEETING_RETENTION_DAYS` (default 90), `PERIODIC_SUMMARY_LOOKBACK_MINUTES` (default 10)
- `SMTP_HOST/PORT/USER/PASS` for email
- `NOTION_TOKEN`, `NOTION_PAGE_ID`
- `CORS_ORIGINS`, `FRONTEND_URL`, `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_PERIOD`

To switch the backend to Ollama locally:
- set `LLM_PROVIDER=ollama`
- make sure Ollama is running on `OLLAMA_BASE_URL` and pull the model named in `OLLAMA_MODEL`
- use a small CPU-friendly  model such as `phi3:mini` or `gemma2:2b` for low-RAM if you dont have a GPU
- increase `OLLAMA_KEEP_ALIVE` if you want the model to stay warm between requests

## Local Development
Backend (Python 3.11):
```bash
python -m venv .venv
.\.venv\Scripts\activate      # PowerShell
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend (Node 20):
```bash
cd frontend
npm install
npm run dev
```
- API base: `http://localhost:8000`
- Frontend dev: `http://localhost:5173`

## Docker
### Quick start (prebuilt images)
Prebuilt images are on Docker Hub:
- Backend: `lazyghost1/kontext-backend`
- Frontend: `lazyghost1/kontext-frontend`

Place a `.env` (copy from `.env.example`) in the repo root so the backend has your keys/secrets.

Save this as `docker-compose.yml` (or adapt your existing one):
```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: kontext_agent
    volumes:
      - postgres_data:/var/lib/postgresql/data

  backend:
    image: lazyghost1/kontext-backend:latest
    env_file: .env
    environment:
      APP_ENV: production
      APP_HOST: 0.0.0.0
      APP_PORT: "8000"
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/kontext_agent
      CHROMA_DIR: /app/chroma_db
      PRELOAD_EMBEDDINGS: "true"
      CORS_ORIGINS: http://localhost
    ports:
      - "8000:8000"
    depends_on:
      - postgres
    volumes:
      - chroma_data:/app/chroma_db

  frontend:
    image: lazyghost1/kontext-frontend:latest
    environment:
      VITE_API_BASE_URL: http://localhost:8000
      VITE_WS_URL: ws://localhost:8000
    ports:
      - "80:80"
    depends_on:
      - backend

volumes:
  postgres_data:
  chroma_data:
```

Run it:
```bash
docker compose up -d
```

### Build locally (optional)
If you prefer to build from source:
```bash
docker compose up --build
```

## API Quick Reference
- `GET /` and `GET /health`
- `GET /metrics` - Prometheus scrape endpoint for LLM telemetry(in the works)
- `POST /auth/signup | /login | /forgot-password | /reset-password`
- `WS /meeting/ws` - send audio; `STOP` to finalize; `ACTION: EMAIL <addr>` or `ACTION: NOTION` to export
- `GET /meeting/history`, `/meeting/{id}/transcript`, `/meeting/{id}/summary`
- `DELETE /meeting/{id}` (hard delete transcript, summaries, embeddings)
- `POST /meeting/{id|recent|any|latest}/chat`
- `POST /chat/query`, `DELETE /chat/history`
- `POST /docs/upload`, `GET /docs/status/{job_id}`, `POST /docs/chat`, `DELETE /docs/clear`
- `WS /voice-chat/ws`

## Data and Storage
- Transcripts and summaries: encrypted in Postgres with retention (`MEETING_RETENTION_DAYS`).
- Vector store: `chroma_db/` (Chroma persistent client).

## Testing
```bash
pytest
```
Tests stub Chroma/RAG for speed; they use SQLite by default unless `DATABASE_URL` is set.

## Contributing
Pull requests are welcome. Quick checklist:
- Fork the repo and create a branch (`git checkout -b feat/your-idea`).
- Backend: Python 3.11, `python -m venv .venv && .\.venv\Scripts\activate`, `pip install -r requirements.txt`, run `pytest`.
- Frontend: Node 20, `cd frontend && npm install && npm run lint`.
- Run apps locally (`uvicorn app.main:app --reload --port 8000` and `npm run dev`). If you change ports, set `VITE_API_BASE_URL` (and `VITE_WS_URL` for sockets) in `frontend/.env.local`.
- Keep PRs focused; include screenshots for UI changes when helpful.
- In the PR description, note the motivation, what changed, and how you tested.

## Troubleshooting
- **Port already in use:** stop the conflicting process (`netstat -ano | findstr :8000`) or change the port and update `VITE_API_BASE_URL`.
- **Slow first start:** embedding model download can take time; set `PRELOAD_EMBEDDINGS=false` to skip upfront (it will lazy-load later).

## Security Notes
- Set strong `JWT_SECRET` and explicit `CORS_ORIGINS` in production.
- Do not commit real `.env` values.
