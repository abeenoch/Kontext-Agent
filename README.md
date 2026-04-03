# Kontext Agent

Full-stack meeting and knowledge assistant with real-time transcription, periodic summaries, RAG search, and voice/chat.

## What’s Inside
- **Backend:** FastAPI (`app/`), Postgres for auth/chat/meeting data (transcripts & summaries encrypted at rest), ChromaDB (`chroma_db/`) for vectors.
- **LLM:** Groq chat completions with configurable model/temperature; PII is scrubbed before prompts.
- **Speech:** Deepgram STT (meetings + voice chat) and TTS.
- **Frontend:** React 19 + Vite + Tailwind (`frontend/`).
- **Integrations:** SMTP email, Notion export, JWT auth with signup/login/reset, rate limiting, meeting delete + retention/TTL.

## Core Features
- **Live meeting WebSocket** (`/meeting/ws`): PCM16 audio (binary or base64), interim/final transcripts, keep-alive + auto reconnect, `STOP` triggers a structured final summary, runtime reconfig via `{"type":"config","sample_rate":16000}`.
- **Summaries:** Periodic delta-based snapshots (last N minutes) plus final Markdown summary; fallback summary if the LLM fails.
- **Post-meeting chat** (`POST /meeting/{id|recent|any|latest}/chat`): RAG over the meeting and cross-meeting context; accepts voice input; commands to email or Notion-export the summary.
- **Document chat** (`POST /docs/chat`): PDF/TXT upload (50 MB) with ingestion jobs, per-tab collections, optional RAG bypass, voice input.
- **General chat** (`POST /chat/query`): Remembers recent history and uses doc context when available; optional voice input.
- **Voice chat socket** (`/voice-chat/ws`): Real-time STT → LLM → TTS with conversation recall.
- **Data hygiene:** PII redaction before LLM calls, encrypted DB columns for transcripts/summaries, meeting retention/TTL and hard delete.

## Environment
Copy `.env.example` to `.env` and set at least:
- `DATABASE_URL` (async SQLAlchemy URI; Postgres via `asyncpg` recommended)
- `GROQ_API_KEY`
- `DEEPGRAM_API_KEY`
- `JWT_SECRET` (>=32 chars in production)
- `ENCRYPTION_KEY` (falls back to `JWT_SECRET`, but set a dedicated key for production)
- `PRELOAD_EMBEDDINGS` (set to `true` to download the embedding model at startup; defaults to `false` to speed container health checks)

Common optional keys:
- `GROQ_MODEL`, `LLM_TEMPERATURE`, `LLM_TIMEOUT`
- `EMBEDDING_MODEL` (defaults to `all-MiniLM-L6-v2`)
- `CHROMA_DIR`
- `MEETING_RETENTION_DAYS` (default 90), `PERIODIC_SUMMARY_LOOKBACK_MINUTES` (default 10)
- `SMTP_HOST/PORT/USER/PASS` for email
- `NOTION_TOKEN`, `NOTION_PAGE_ID`
- `CORS_ORIGINS`, `FRONTEND_URL`, `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_PERIOD`

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
```bash
docker compose up --build
```
Services:
- `postgres` (16) with DB `kontext_agent`, user/password `postgres` (port 5432 exposed)
- `backend` (FastAPI)
- `frontend` (Vite dev server)

Backend is pre-wired to Postgres via:
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/kontext_agent
```
Persistent data:
- Vector store: `./chroma_db` ↔ `/app/chroma_db`
- Transcripts/summaries live in the DB (no host volume needed for them)

## API Quick Reference
- `GET /` and `GET /health`
- `POST /auth/signup | /login | /forgot-password | /reset-password`
- `WS /meeting/ws` — send audio; `STOP` to finalize; `ACTION: EMAIL <addr>` or `ACTION: NOTION` to export
- `GET /meeting/history`, `/meeting/{id}/transcript`, `/meeting/{id}/summary`
- `DELETE /meeting/{id}` (hard delete transcript, summaries, embeddings)
- `POST /meeting/{id|recent|any|latest}/chat`
- `POST /chat/query`, `DELETE /chat/history`
- `POST /docs/upload`, `GET /docs/status/{job_id}`, `POST /docs/chat`, `DELETE /docs/clear`
- `WS /voice-chat/ws`

## Data & Storage
- Transcripts/summaries: encrypted in Postgres with retention (`MEETING_RETENTION_DAYS`) and user-driven delete.
- Vector store: `chroma_db/` (Chroma persistent client).
- Tables auto-created on startup (`app/services/chat_memory.py`).

## Testing
```bash
pytest
```
Tests stub Chroma/RAG for speed; they use SQLite by default unless `DATABASE_URL` is set.

## Security Notes
- Set strong `JWT_SECRET` and explicit `CORS_ORIGINS` in production.
- Keep `ENCRYPTION_KEY` private; rotate it with a planned re-encrypt/migrate strategy.
- Do not commit real `.env` values.
