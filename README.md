# Kontext Agent

Full‑stack meeting and knowledge assistant with real‑time transcription, periodic summaries, RAG search, and voice/chat.

## What’s Inside

- **Backend:** FastAPI (`app/`), async Postgres for auth/chat/meeting data, ChromaDB (`chroma_db/`) for vectors, transcript/summary files under `data/meeting_transcripts`.
- **LLM:** Groq chat completions (configurable model/temperature).
- **Speech:** Deepgram STT (meeting + voice chat) and TTS for spoken replies.
- **Frontend:** React 19 + Vite + Tailwind (`frontend/`).
- **Integrations:** SMTP email, Notion export, JWT auth with signup/login/reset, basic rate limiting.

## Core Features

- **Live meeting WebSocket** (`/meeting/ws`): PCM16 audio (binary preferred; base64 text supported), interim/final transcripts, keep‑alive + auto reconnect, `STOP` triggers a structured final summary. Supports runtime reconfig via `{"type":"config","sample_rate":16000}`.
- **Summaries:** Periodic snapshots every 5 minutes plus final Markdown summary with actions/decisions. Fallback summary is generated from the transcript if the LLM fails.
- **Post‑meeting chat** (`POST /meeting/{id|recent|any|latest}/chat`): RAG over the meeting and cross‑meeting context; accepts voice input; built‑in commands to email or Notion‑export the summary.
- **Document chat** (`POST /docs/chat`): PDF/TXT upload (50 MB) with background ingestion jobs (`POST /docs/upload`, `GET /docs/status/{job_id}`), per‑tab collections, optional RAG bypass, voice input.
- **General chat** (`POST /chat/query`): Remembers recent history, auto‑uses doc context when available, optional voice input.
- **Voice chat socket** (`/voice-chat/ws`): Real‑time STT → LLM → TTS replies with conversation history recall.
- **Auth flows:** Signup/login, password reset via email tokens, JWT for REST and WebSockets (`?token=` fallback).

## Environment
S
Copy `.env.example` to `.env` and set at least:

- `DATABASE_URL` (async SQLAlchemy URI; tested with Postgres via `asyncpg`)
- `GROQ_API_KEY`
- `DEEPGRAM_API_KEY`
- `JWT_SECRET` (>=32 chars in production)

Common optional keys:

- `GROQ_MODEL`, `LLM_TEMPERATURE`, `LLM_TIMEOUT`
- `EMBEDDING_MODEL` (defaults to `all-MiniLM-L6-v2`; multilingual example in `.env.example`)
- `CHROMA_DIR`, `TRANSCRIPTS_DIR`
- `SMTP_HOST/PORT/USER/PASS` for email
- `NOTION_TOKEN`, `NOTION_PAGE_ID`
- `CORS_ORIGINS`, `FRONTEND_URL`, rate limits (`RATE_LIMIT_REQUESTS`, `RATE_LIMIT_PERIOD`)



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

Services launched:
- `postgres` (16) with DB `kontext_agent`, user/password `postgres` (port 5432 exposed)
- `backend` (FastAPI)
- `frontend` (Vite dev server)

Backend is pre-wired to the Postgres container via:
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/kontext_agent
```
Mounts persist vector DB (`./chroma_db`) and transcripts (`./data`). Override DB creds/URL in `.env` if you change the Postgres service settings.

## API Quick Reference

- `GET /` and `GET /health` – liveness.
- `POST /auth/signup | /login | /forgot-password | /reset-password`
- `WS /meeting/ws` – send audio; `STOP` to finalize; `ACTION: EMAIL <addr>` or `ACTION: NOTION` to trigger exports.
- `GET /meeting/history`, `/meeting/{id}/transcript`, `/meeting/{id}/summary`
- `POST /meeting/{id|recent|any|latest}/chat`
- `POST /chat/query`, `DELETE /chat/history`
- `POST /docs/upload` (multipart, `tab_id` required), `GET /docs/status/{job_id}`, `POST /docs/chat`, `DELETE /docs/clear`
- `WS /voice-chat/ws`

## Data & Storage

- Transcripts/summaries: `data/meeting_transcripts/`
- Vector store: `chroma_db/`
- Database tables are auto‑created on startup (`app/services/chat_memory.py`).

## Testing

```bash
pip install -r requirements.txt
pytest
```

Tests stub Chroma and RAG to keep them lightweight, but still require a valid `DATABASE_URL` reachable from the test runner.

## Security Notes

- Set a strong `JWT_SECRET` and non‑wildcard `CORS_ORIGINS` in production.
- Never commit real `.env` values.
 
