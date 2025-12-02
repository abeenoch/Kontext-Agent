# Kontext Meeting Agent 🎙️

Real-time meeting transcription, summarization, and integration platform powered by AI.

Kontext is a self-hosted meeting assistant that captures audio from your microphone, transcribes it in real-time using OpenAI's Whisper, generates intelligent summaries with Groq's LLMs, and automatically sends them to email, Notion on request, or stores them locally.


**Enable streaming:** Set `ENABLE_STREAMING=true` in `.env`

- **🎙️ Real-time Audio Capture**: WebRTC-based audio streaming from browser to backend
- **📝 Transcription**: Streaming transcription using faster-Whisper (CPU-friendly)
- **✂️ Smart Summaries**: Automatic meeting summaries with key points, decisions, and action items
- **📧 Email Integration**: Send meeting summaries directly to team members via email
- **📘 Notion Integration**: Push summaries to Notion databases for team documentation
- **🔍 RAG Search**: Query meeting content using semantic search with Pinecone
- **💬 Post-Meeting Chat**: Ask questions about meetings after they end
- **📊 Local Storage**: SQLite database keeps all data on your server
- **🚀 Docker Ready**: One-command deployment with Docker Compose

## Features

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Backend** | FastAPI + Uvicorn | Real-time WebSocket streaming |
| **Speech-to-Text** | faster-Whisper (base/medium) | CPU-efficient transcription |
| **Summarization** | Groq API (Llama 70B) | High-quality meeting summaries |
| **Embeddings** | Sentence-Transformers | Semantic search for meeting content |
| **Vector DB** | Pinecone | Store and query meeting embeddings |
| **Frontend** | Vanilla JavaScript + HTML | Lightweight, no frameworks |
| **Database** | SQLite | Local persistent storage |
| **Email** | SMTP (Gmail) | Send summaries to team |
| **Notion API** | Official Python Client | Push to shared Notion databases |


---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Groq API key (free at https://console.groq.com/keys)
- (Optional) Notion API token
- (Optional) Email credentials for sending transcripts

### Setup

1. **Clone the repository**
```bash
git clone <repo-url>
cd Kontext-Agent
```

2. **Create `.env` file**
```bash
cp .env.example .env
```

3. **Configure environment variables** (edit `.env`)
```env
# Groq API (required for streaming mode)
GROQ_API_KEY=your_groq_api_key_here

# Streaming configuration
ENABLE_STREAMING=true           # Set to false for local batch mode
FRAME_SIZE_MS=20               # Audio frame size in milliseconds
SUMMARY_INTERVAL_MIN=1         # Update summary every 1 minute

# Notion integration (optional)
NOTION_API_TOKEN=your_notion_token
NOTION_DATABASE_ID=your_database_id

# Email integration (optional)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SENDER_EMAIL=your_email@gmail.com
SENDER_PASSWORD=your_app_password
```

4. **Start the application**
```bash
docker-compose up -d
```

5. **Access the UI**
```
http://localhost:8000
```

---

## Usage

### Starting a Meeting

1. Open http://localhost:8000
2. Click **Start Recording**
3. Allow microphone access when prompted
4. Speak naturally - transcription happens in real-time
5. See live captions with:
   - 🔴 Gray italic text = interim (being processed)
   - ⚫ Black bold text = final (confirmed)

### During Meeting

- **Transcripts** appear in real-time (streaming mode)
- **Summaries** auto-update every 1 minute
- **Live indicator** shows when meeting is active

### After Meeting

- Click **Stop Recording**
- Transcript and summary automatically saved
- Email sent (if configured)
- Notion database updated (if configured)

---

## Configuration

### Streaming vs Batch Mode

#### Streaming Mode (Default - Fast)
```env
ENABLE_STREAMING=true
GROQ_API_KEY=your_groq_api_key_here
FRAME_SIZE_MS=20
SUMMARY_INTERVAL_MIN=1
```
- **Pros**: 100x faster, real-time, low memory
- **Cons**: Requires API key, rate limited on free tier
- **Best for**: Live meetings, demos, presentations

#### Batch Mode (Local - Privacy)
```env
ENABLE_STREAMING=false
GROQ_API_KEY=    # Not needed
SUMMARY_INTERVAL_MIN=10
```
- **Pros**: No API needed, unlimited, local processing
- **Cons**: 30-60s latency, high memory (2-3GB), slow startup
- **Best for**: Privacy-first, offline, recorded audio files

### Audio Configuration

```env
# Frame size (20ms = 320 samples at 16kHz)
FRAME_SIZE_MS=20          # Recommended: 20-40ms
FRAME_SIZE_MS=10          # Faster but more overhead
FRAME_SIZE_MS=40          # Slower but less overhead

# Summary interval
SUMMARY_INTERVAL_MIN=1    # Streaming mode
SUMMARY_INTERVAL_MIN=10   # Batch mode
```

### API Integration

#### Groq Streaming API
```env
GROQ_API_KEY=your_key_here
ENABLE_STREAMING=true
```
- Get free key: https://console.groq.com/keys
- Free tier: 30 requests/minute (sufficient for ~6 hours of meetings)
- No setup needed beyond API key

#### Notion Integration
```env
NOTION_API_TOKEN=your_token
NOTION_DATABASE_ID=your_database_id
```

#### Email Integration
```env
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SENDER_EMAIL=your_email@gmail.com
SENDER_PASSWORD=your_app_password
```

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────┐
│             Web UI (index.html)                      │
│  • Audio capture (16ms frames in streaming mode)    │
│  • Real-time transcript display                     │
│  • Meeting controls                                 │
└────────────────┬────────────────────────────────────┘
                 │ WebSocket (AUDIO_FRAME)
                 ▼
┌─────────────────────────────────────────────────────┐
│        WebSocket Handler (websocket.py)             │
│  • Streaming transcription worker                   │
│  • Batch transcription worker (fallback)            │
│  • Broadcast partial/final results                  │
└────────────────┬────────────────────────────────────┘
                 │
        ┌────────┴────────┐
        ▼                 ▼
   ┌─────────┐      ┌──────────┐
   │   Groq  │      │  Local   │
   │  API    │      │  Whisper │
   │(Stream) │      │ (Batch)  │
   └────┬────┘      └────┬─────┘
        └────────┬───────┘
                 ▼
     ┌───────────────────────┐
     │  Audio Processing     │
     │  • Normalization      │
     │  • Noise handling     │
     │  • Format conversion  │
     └───────────────────────┘
                 │
        ┌────────┴────────┐
        ▼                 ▼
   ┌─────────┐      ┌──────────────┐
   │ Database │     │ Summarizer    │
   │ Storage  │     │ (Every 1 min) │
   └──────────┘     └─────┬────────┘
                          ▼
                   ┌──────────────┐
                   │ Integrations │
                   │ • Email      │
                   │ • Notion     │
                   │ • Services   │
                   └──────────────┘
```

### Data Flow (Streaming Mode)

```
Speech → Browser (16ms frames) → WebSocket
  ↓
Groq API (100-300ms) → Partial results
  ↓
UI (real-time captions) → Database
  ↓
Summarizer (1-min interval) → Email/Notion
```


---

```






## File Structure

```
Kontext-Agent/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app
│   ├── config.py               # Configuration
│   ├── database.py             # Database operations
│   ├── api/
│   │   ├── routes.py           # HTTP endpoints
│   │   └── websocket.py        # WebSocket handlers
│   ├── core/
│   │   ├── audio_processor.py  # Audio normalization
│   │   ├── transcriber.py      # Local Whisper
│   │   ├── rag_engine.py       # RAG for summaries
│   │   └── summarizer.py       # Summary generation
│   ├── services/
│   │   ├── streaming_transcriber.py  # Groq streaming
│   │   ├── meeting_service.py
│   │   ├── email_service.py
│   │   ├── notion_service.py
│   │   └── meeting_service.py
│   ├── models/
│   │   └── schemas.py          # Pydantic models
│   └── ui/
│       ├── index.html          # Web UI
│       └── audio_recorder.py
├── data/
│   └── meeting_transcripts/    # Stored transcripts
├── logs/                       # Application logs
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── start_server.py
└── README.md
```





## Contributing 🤝

Contributions welcome! Please:

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request



- **Email**: funboy.ea@gmail.com

## Why I Built This 🎯

I attend multiple meetings daily at Payvite and other commitments. Traditional meeting assistants are expensive. I wanted:

- ✅ **Privacy**: All data stays on my server
- ✅ **Cost**: No monthly subscriptions
- ✅ **Control**: Integrate with our tools (Notion, email)
- ✅ **Simplicity**: One-click to start recording
- ✅ **Extensibility**: Add new integrations easily

 Maybe it'll help you too!

---


