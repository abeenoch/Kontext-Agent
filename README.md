# Kontext Agent

Full-stack meeting and knowledge assistant with real-time transcription, RAG search, and voice/chat UX.

## What You Get
- Backend: FastAPI (`app/`), Postgres for auth/chat/meetings, ChromaDB (`chroma_db/`) for vectors, transcripts/summaries under `data/meeting_transcripts/`.
- LLM: Groq chat completions (configurable model, temperature, timeout).
- Speech: Deepgram STT (meeting + voice chat) and TTS replies.
- Frontend: React 19 + Vite + Tailwind (`frontend/`).
- Integrations: SMTP email, Notion export, JWT auth (signup/login/reset), rate limiting.

## Project Layout (high touch)
- `app/main.py` - app factory, CORS, router wiring.
- `app/routes/meeting.py` - live meeting socket, periodic/final summaries, post-meeting chat.
- `app/routes/voice_chat.py` - duplex voice chat (STT -> LLM -> TTS).
- `app/routes/docs.py` - uploads, ingestion jobs, doc chat.
- `app/routes/chat.py` - general chat with doc context.
- `app/auth.py`, `app/routes/auth.py` - JWT + signup/login/reset.
- `app/services/*` - Deepgram, Groq client, embeddings, vector store, integrations.
- Frontend pages: `frontend/src/pages/MeetingPage.jsx`, `ChatPage.jsx`, `LoginPage.jsx`, `SignupPage.jsx`.

## Prerequisites
- Docker 24+ with compose plugin (easiest), or:
  - Python 3.11+
  - Node 20+
  - Postgres 14+ reachable via TCP
- API keys: Groq (`GROQ_API_KEY`) and Deepgram (`DEEPGRAM_API_KEY`)

## Quick Start (Docker)
1) Copy env and set secrets:
```
cp .env.example .env
```
   Required: `GROQ_API_KEY`, `DEEPGRAM_API_KEY`, `JWT_SECRET` (>=32 chars).

2) Launch stack:
```
docker compose up --build
```

3) Open `http://localhost:5173`, sign up, start a meeting or chat.

Compose services:
- `postgres` (16) db: `kontext_agent`, user/pass: `postgres` (port 5432)
- `backend` (FastAPI) on `http://localhost:8000`
- `frontend` (Vite dev) on `http://localhost:5173`

Backend DB wiring (already set in compose):
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/kontext_agent
```
Persistent data: `postgres_data` volume, vectors in `./chroma_db`, transcripts in `./data/meeting_transcripts`.
Ports: backend 8000, frontend 5173, Postgres 5432.

## Local Development (manual)
Backend:
```
python -m venv .venv
.\.venv\Scripts\activate   # or source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+asyncpg://<user>:<pass>@<host>:5432/kontext_agent
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:
```
cd frontend
npm install
npm run dev
```

Defaults: API `http://localhost:8000`, frontend `http://localhost:5173`.

If Postgres is local, create the DB first: `createdb kontext_agent` (or via psql).
To run Postgres in Docker locally:
```
docker run -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=kontext_agent postgres:16
```

## Environment Variables
Required:
- `DATABASE_URL` (async SQLAlchemy URI)
- `GROQ_API_KEY`
- `DEEPGRAM_API_KEY`
- `JWT_SECRET` (use 32+ chars in production)

Common optional:
- `GROQ_MODEL`, `LLM_TEMPERATURE`, `LLM_TIMEOUT`
- `EMBEDDING_MODEL` (default `all-MiniLM-L6-v2`; multilingual example in `.env.example`)
- `CHROMA_DIR`, `TRANSCRIPTS_DIR`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`
- `NOTION_TOKEN`, `NOTION_PAGE_ID`
- `CORS_ORIGINS`, `FRONTEND_URL`
- `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_PERIOD`
- `LOG_LEVEL` (default INFO)

## Feature Map
- Live meeting socket: `WS /meeting/ws`
  - Send PCM16 audio (binary preferred; base64 text accepted).
  - `STOP` ends session and triggers structured final summary.
  - `{"type":"config","sample_rate":16000}` to change sample rate.
  - `ACTION: EMAIL <addr>` or `ACTION: NOTION` to export last summary.
  - Periodic summaries every 5 minutes (`periodic_summary`), final summary as `final_summary`.
- Post-meeting chat: `POST /meeting/{id|recent|any|latest}/chat` (RAG over meeting and cross-meeting context; voice input allowed).
- Docs chat: `POST /docs/chat` with optional RAG (`use_rag`), PDF/TXT uploads up to 50 MB via `POST /docs/upload`, job status at `GET /docs/status/{job_id}`, per-tab collections, voice input.
- General chat: `POST /chat/query`, `DELETE /chat/history`.
- Voice chat: `WS /voice-chat/ws` (real-time STT -> LLM -> TTS).
- Auth: `POST /auth/signup`, `/login`, `/forgot-password`, `/reset-password` (JWT for REST; `?token=` accepted on WebSockets).

## Data & Storage
- Postgres: users, auth, chat history, meeting transcripts/summaries, doc ingestion jobs.
- ChromaDB: embeddings for docs and meetings (`./chroma_db`).
- Files: transcripts/summaries under `data/meeting_transcripts/`.
- Tables auto-create on startup (`app/services/chat_memory.py`).

## Build for Production
- Backend: run under `uvicorn` or another ASGI server (`uvicorn app.main:app --host 0.0.0.0 --port 8000`).
- Frontend: `npm run build`, then serve `frontend/dist` behind a static host or CDN; set `VITE_API_BASE_URL` and `VITE_WS_URL` at build time.
- Reverse proxy: terminate TLS and forward to backend 8000 and your static frontend.

## Testing
```
pip install -r requirements.txt
pytest
```
Tests stub Chroma/RAG but still need a reachable Postgres via `DATABASE_URL`.

## Security
- Use a strong `JWT_SECRET`; set explicit `CORS_ORIGINS` in production (avoid `*`).
- Do not commit real `.env` values.
- SMTP/Notion are optional; flows degrade gracefully when unset.

## Troubleshooting
- First run may download the embedding model (sentence-transformers); keep network open.
- If Groq/Deepgram keys are missing, related features will error; check logs.
- If LLM calls fail, meeting summaries fall back to transcript-based output with a clear message.
- Meeting audio tips: prefer 16 kHz mono PCM16; if interim results pause, Deepgram keepalives handle idle gaps.
