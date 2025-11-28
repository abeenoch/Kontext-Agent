# Kontext Meeting Agent 🎤

**Automatically transcribe, summarize, and distribute meeting notes** — No expensive SaaS subscription required.

Kontext is a self-hosted meeting assistant that captures audio from your microphone, transcribes it in real-time using OpenAI's Whisper, generates intelligent summaries with Groq's LLMs, and automatically sends them to email, Notion, or stores them locally.

Built for teams who want **privacy, control, and cost-efficiency**.

## Features ✨

- **🎙️ Real-time Audio Capture**: WebRTC-based audio streaming from browser to backend
- **📝 Live Transcription**: Streaming transcription using faster-Whisper (CPU-friendly)
- **✂️ Smart Summaries**: Automatic meeting summaries with key points, decisions, and action items
- **📧 Email Integration**: Send meeting summaries directly to team members via email
- **📘 Notion Integration**: Push summaries to Notion databases for team documentation
- **🔍 RAG Search**: Query meeting content using semantic search with Pinecone
- **💬 Post-Meeting Chat**: Ask questions about meetings after they end
- **📊 Local Storage**: SQLite database keeps all data on your server
- **🚀 Docker Ready**: One-command deployment with Docker Compose

## Tech Stack 🛠️

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Backend** | FastAPI + Uvicorn | Real-time WebSocket streaming |
| **Speech-to-Text** | faster-Whisper (base/medium) | CPU-efficient transcription |
| **Summarization** | Groq API (Llama 70B) | High-quality meeting summaries |
| **Embeddings** | Sentence-Transformers | Semantic search for meeting content |
| **Vector DB** | Pinecone | Store and query meeting embeddings |
| **Frontend** | Vanilla JavaScript + HTML | Lightweight, no frameworks |
| **Database** | SQLite | Local persistent storage |
| **Email** | SMTP (Gmail, Office365, etc) | Send summaries to team |
| **Notion API** | Official Python Client | Push to shared Notion databases |

## Quick Start 🚀

### Option 1: Docker (Recommended)

```bash
# Clone repository
git clone https://github.com/abeenoch/kontext-agent.git
cd kontext-agent

# Copy and configure .env
cp .env.example .env
# Edit .env with your API keys

# Start with Docker Compose
docker-compose up -d

# Access at http://localhost:8000
```

### Option 2: Local Development

```bash
# Install Python 3.13+
python --version  # Should be 3.13 or higher

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Start server
python start_server.py

# Open http://localhost:8000 in browser
```

## Configuration 🔧

### Required API Keys

Get these free or as trial:

1. **Groq API** (Free, high-rate limits)
   - Sign up: https://console.groq.com/
   - Get API key for Llama 70B access

2. **Gmail SMTP** (For email sending)
   - Enable 2FA on Google Account
   - Create app password: https://myaccount.google.com/apppasswords
   - Use as `SMTP_PASSWORD` in .env

3. **Notion Integration** (Optional, for Notion sync)
   - Create integration: https://www.notion.com/my-integrations
   - Get API key and database ID
   - Share the database with your integration in Notion

4. **Pinecone** (Optional, for semantic search)
   - Create free account: https://www.pinecone.io
   - Get API key and environment

### Environment Variables

```env
# Server
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO

# Whisper (Speech-to-Text)
WHISPER_MODEL=medium          # Options: tiny, base, small, medium, large-v2
WHISPER_DEVICE=cpu            # Options: cpu, cuda (GPU)
WHISPER_COMPUTE_TYPE=int8     # Options: int8, float16, float32

# Groq (LLM for summaries)
GROQ_API_KEY=your_key_here
GROQ_MODEL=openai/gpt-oss-20b # Or: mixtral-8x7b-32768, llama-3.1-8b-instant

# Email (SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=Meeting Agent <your-email@gmail.com>
SMTP_USE_TLS=true

# Notion (Optional)
NOTION_API_KEY=ntn_...
NOTION_DATABASE_ID=29e7f671-a347-804e-82ef-df60c0939d83

# Pinecone (Optional)
PINECONE_API_KEY=pcsk_...
PINECONE_INDEX_NAME=meeting-agent

# Audio Settings
SAMPLE_RATE=16000
TRANSCRIPTION_WINDOW_SEC=60
MIN_AUDIO_DURATION_SEC=10
```

## Usage 📖

### 1. Start a Meeting

1. Open http://localhost:8000 in your browser
2. Click **"Start Meeting"**
3. Allow microphone access
4. Speak naturally — transcriptions appear in real-time

### 2. During Meeting

- **Live Transcripts**: See speech being transcribed in real-time
- **Periodic Summaries**: Every 10 minutes, a summary appears
- **Audio Status**: Shows capture status and audio levels

### 3. End Meeting

Click **"Stop Meeting"** when done. The system will:
- Transcribe any remaining audio
- Generate final comprehensive summary
- Index to Pinecone (for semantic search)
- Show final summary

### 4. Post-Meeting Actions

After meeting ends, you can:

**Send Email:**
```
"Send summary to john@example.com, alice@example.com"
```

**Push to Notion:**
```
"Push to Notion"
```

**Ask Questions:**
```
"What were the key action items?"
"Tell me about budget discussions"
```

## Performance Metrics 📊

| Metric | Value | Notes |
|--------|-------|-------|
| **Transcription Speed** | ~30s audio in 60s | Depends on CPU, longer audio = longer time |
| **Transcription Accuracy** | 92-95% (Medium model) | Higher with larger Whisper model |
| **Summary Generation** | 5-10 seconds | Via Groq LLM |
| **Email Send** | <5 seconds | Via SMTP |
| **Notion Push** | 5-10 seconds | API rate limited |
| **Memory Usage** | ~2-3GB | During transcription |
| **Disk Usage** | ~500MB per 1hr meeting | Compressed storage |

## Architecture 🏗️

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser (Frontend)                   │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  WebAudioAPI → PCM Audio → Base64 Encoding              ││
│  │  WebSocket Connection (ws://localhost:8000/ws/meeting)  ││
│  └──────────────────┬──────────────────────────────────────┘│
└─────────────────────┼──────────────────────────────────────┘
                      │ Audio Chunks (PCM)
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                          │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  WebSocket Handler                                       ││
│  │  ├─ Audio Buffering (AudioBuffer)                       ││
│  │  ├─ Transcription Worker (10s intervals)                ││
│  │  └─ Summarization Worker (10min intervals)              ││
│  └──────────────────┬──────────────────────────────────────┘│
│                     │                                        │
│  ┌──────────────┬───┴─────────┬──────────────┐              │
│  │              │             │              │              │
│  ▼              ▼             ▼              ▼              │
│ Whisper    Groq LLM   Sentence         SQLite DB            │
│ (CPU)     (Summary)   Transformers   (Meetings)             │
│           (via API)    (Embeddings)                          │
│                             │                               │
│                             ▼                               │
│                        Pinecone                             │
│                      (Vector Search)                        │
└─────────────────────────────────────────────────────────────┘
          │                  │                 │
          ▼                  ▼                 ▼
        Email             Notion           Chat/Query
       (SMTP)             (API)           (RAG + LLM)
```

## Troubleshooting 🐛

### Transcription is Gibberish

**Cause**: Audio too quiet or browser processing removing speech

**Solutions**:
1. Check microphone volume in system settings
2. Ensure `echoCancellation: false` in browser (already set)
3. Try speaking closer to microphone
4. Check logs for `Auto-normalized` messages

### Meeting ends slowly (long wait)

**Cause**: Large unprocessed audio buffer at end of meeting

**Solution**: Fixed in v1.1 with progressive processing. Audio is now transcribed in 60-second chunks instead of all-at-once.

### Notion integration fails

**Cause**: Database not shared with integration

**Solution**:
1. Open the Notion database
2. Click `•••` (three dots) → "Connections"
3. Add your integration (search by name)
4. Ensure database ID in .env is correct (with hyphens)

### Email not sending

**Cause**: Gmail app password or SMTP settings wrong

**Solution**:
1. Enable 2FA on Google Account
2. Create app-specific password at https://myaccount.google.com/apppasswords
3. Use that password (not your Google password) in .env
4. Ensure SMTP settings match your email provider

## Development 👨‍💻

### Project Structure

```
kontext-agent/
├── app/
│   ├── main.py              # FastAPI app, startup/shutdown
│   ├── config.py            # Settings management
│   ├── database.py          # SQLite operations
│   ├── api/
│   │   ├── routes.py        # REST endpoints
│   │   └── websocket.py     # WebSocket handler (main logic)
│   ├── core/
│   │   ├── audio_processor.py    # Audio buffering
│   │   ├── transcriber.py        # Whisper wrapper
│   │   ├── summarizer.py         # Groq LLM summaries
│   │   └── rag_engine.py         # Pinecone search
│   ├── services/
│   │   ├── email_service.py      # Email sending
│   │   ├── notion_service.py     # Notion API
│   │   └── meeting_service.py
│   ├── models/
│   │   └── schemas.py       # Pydantic models
│   └── ui/
│       ├── index.html       # Frontend
│       └── audio_recorder.py # CLI audio recorder
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env                     # Configuration
└── README.md
```

### Running Tests

```bash
# Run unit tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=app --cov-report=html
```

### Adding Features

1. Create a new service in `app/services/`
2. Add integration logic to `app/api/websocket.py`
3. Update `.env` with new config vars
4. Add tests in `tests/`
5. Document in README

## Known Limitations ⚠️

1. **Single meeting per connection**: Can't run multiple simultaneous meetings (easily fixable)
2. **CPU transcription only**: Whisper on CPU is slower than GPU
3. **No user authentication**: Add your own auth layer before deploying publicly
4. **Browser-only audio**: CLI recorder (audio_recorder.py) available for scripting
5. **English only**: Currently optimized for English; multilingual support via Whisper

## Future Roadmap 🗺️

- [ ] Multi-user support with authentication
- [ ] Speaker diarization (identify who spoke when)
- [ ] Real-time translation to other languages
- [ ] Slack integration for instant notifications
- [ ] Meeting sentiment analysis
- [ ] Custom summary templates
- [ ] Batch processing of external audio files
- [ ] Mobile app for remote meetings
- [ ] Advanced analytics dashboard

## Cost Breakdown 💰

**Monthly cost (for 10 meetings/week, 1hr each):**

| Service | Cost | Notes |
|---------|------|-------|
| Groq LLM | $0 | Free tier covers ~1000 requests/day |
| Whisper | Self-hosted | One-time download |
| Pinecone | $0 | Free tier covers ~100k vectors |
| Email | $0 | Gmail SMTP is free |
| Notion | $0 | Free tier covers 1000 blocks/month |
| **Total** | **$0** | ✅ Completely free! |

Compare to:
- **Otter.ai**: $10-25/month
- **Rev**: $0.25-1/minute transcription
- **Fireflies.ai**: $10-50/month
- **Kontext**: $0 (self-hosted)

## Contributing 🤝

Contributions welcome! Please:

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request

## License 📄

MIT License - see LICENSE file for details

## Support 💬

- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Email**: support@kontext.local

## Why I Built This 🎯

I attend multiple meetings daily at Payvite and other commitments. Traditional meeting assistants are expensive and lock data behind paywalls. I wanted:

- ✅ **Privacy**: All data stays on my server
- ✅ **Cost**: No monthly subscriptions
- ✅ **Control**: Integrate with our tools (Notion, email)
- ✅ **Simplicity**: One-click to start recording
- ✅ **Extensibility**: Add new integrations easily

So I built Kontext — and it's been a game-changer for team documentation. Maybe it'll help you too!

---

**Built with ❤️ by Payvite team**

Questions? Open an issue or reach out!
