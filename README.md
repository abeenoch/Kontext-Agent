# Kontext Agent

Kontext Agent is a full-stack meeting and knowledge assistant.

## Architecture

- Backend: FastAPI (`app/`)
- Frontend: React + Vite (`frontend/`)
- Realtime STT/TTS: Deepgram
- LLM: Groq-compatible chat completions
- Memory: SQLite (`chat_memory.db`) via async access
- RAG store: ChromaDB (`chroma_db/`)

## Core Features

- Realtime meeting transcription over WebSocket
- Periodic meeting summaries every 5 minutes
- Final structured summary on meeting stop
- Post-meeting chat over transcript context
- Email + Notion export for summaries
- Document upload (PDF/TXT) and RAG chat

## Repository Layout

- `app/main.py`: FastAPI app and router wiring
- `app/routes/meeting.py`: meeting WebSocket + summary + post-meeting chat
- `app/routes/chat.py`: general chat + optional voice input
- `app/routes/docs.py`: document ingestion and docs chat
- `app/services/deepgram.py`: STT/TTS wrapper and stream controls
- `app/services/summarizer.py`: periodic summary scheduler
- `app/services/integrations_service.py`: email + Notion exports
- `frontend/src/pages/MeetingPage.jsx`: meeting UI
- `frontend/src/pages/ChatPage.jsx`: chat + upload UI

## Environment Variables

Create `.env` in project root.

Required for full functionality:

- `GROQ_API_KEY`
- `DEEPGRAM_API_KEY`
- `JWT_SECRET`

Optional integrations:

- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`
- `NOTION_TOKEN`, `NOTION_PAGE_ID`

Common runtime:

- `APP_HOST` (default: `0.0.0.0`)
- `APP_PORT` (default: `8000`)
- `CHROMA_DIR` (default: `./chroma_db`)
- `CHAT_DB_PATH` (default: `./chat_memory.db`)

## Local Development

### Backend

```bash
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend dev URL: `http://localhost:5173`
Backend API URL: `http://localhost:8000`

## Docker

### Build and run with Compose

```bash
docker compose up --build
```

Services:

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`

## Health and Smoke Checks

Backend health:

```bash
curl http://localhost:8000/health
```

Frontend production build check:

```bash
cd frontend
npm run build
```

Python syntax check:

```bash
python -m py_compile app/main.py
```

## API Notes

- Realtime meeting socket: `ws://localhost:8000/meeting/ws`
- Meeting stream accepts:
  - Binary frames: PCM16 bytes (preferred)
  - Text frames: control messages (`STOP`, config/actions)
- Periodic summaries are emitted as `periodic_summary`
- End-of-meeting summary is emitted as `final_summary`

## Security Notes

- Do not commit `.env` with real secrets.
- Restrict CORS and JWT settings in production.
- Rotate API keys and SMTP credentials regularly.
