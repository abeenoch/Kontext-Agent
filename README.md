# Kontext Meeting Agent 🎙️

Real-time meeting transcription, summarization, and integration platform powered by AI.


| Feature | Batch Mode | Streaming Mode |
|---------|-----------|-----------------|
| **Latency** | 30-60 seconds | 100-300ms |
| **Speed** | 📦 Batch processing | ⚡ Real-time |
| **Memory** | 2-3GB | 500-800MB |
| **First Word** | After 30-60s | Instant |
| **Summaries** | Every 10 minutes | Every 1 minute |
| **API** | Local Whisper | Groq Streaming |

**Enable streaming:** Set `ENABLE_STREAMING=true` in `.env`

---

## Features

✨ **Core Capabilities**
- 🎙️ Real-time audio transcription (local Whisper or Groq streaming API)
- 📝 Intelligent meeting summaries (updated every 1-10 minutes)
- 📧 Automatic email delivery of transcripts and summaries
- 📔 Notion integration (save summaries to Notion database)
- 🌐 Web UI for meeting recording and playback
- 💾 Persistent storage of meeting history

🚀 **Performance** (Streaming Mode)
- 100-300ms latency (100x faster than batch)
- Real-time partial transcripts
- Live captions with interim results
- Automatic API fallback to batch mode

🔧 **Developer Friendly**
- WebSocket streaming for real-time updates
- FastAPI backend with async support
- Docker & docker-compose ready
- Single toggle for batch/streaming mode
- Comprehensive logging

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


---

## Deployment

### Docker Compose (Recommended)

```bash
# Build and start
docker-compose up -d

# View logs
docker logs -f kontext-meeting-agent

# Stop
docker-compose down
```

### Docker Only

```bash
# Build image
docker build -t kontext-agent .

# Run container
docker run -d \
  -p 8000:8000 \
  -e GROQ_API_KEY=your_key \
  -e ENABLE_STREAMING=true \
  -v ./data:/app/data \
  kontext-agent
```

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GROQ_API_KEY=your_key
export ENABLE_STREAMING=true

# Run server
python start_server.py

# Access at http://localhost:8000
```

---

## Troubleshooting

### Streaming transcription not working

**Problem**: Transcripts not appearing in real-time
**Solution**:
1. Verify Groq API key: `echo $GROQ_API_KEY` (should show your key)
2. Check browser console for `TRANSCRIPT_PARTIAL` messages
3. Ensure WebSocket connection is open: check DevTools → Network → WS
4. Fallback to batch mode: set `ENABLE_STREAMING=false`

### High memory usage

**Problem**: Memory spike to 2-3GB
**Solution**:
- This is batch mode behavior (streaming uses 500-800MB)
- To enable streaming: set `ENABLE_STREAMING=true` and add `GROQ_API_KEY`
- Restart container: `docker-compose restart`



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

---

## API Reference

### WebSocket Events

#### Client → Server

```javascript
// Start meeting
{ type: "START_MEETING", data: { meeting_id: "...", title: "..." } }

// Audio frame (16ms)
{ type: "AUDIO_FRAME", data: { audio: Uint8Array, ... } }

// Stop meeting
{ type: "STOP_MEETING", data: {} }
```

#### Server → Client

```javascript
// Interim transcript
{ type: "TRANSCRIPT_PARTIAL", data: { text: "...", is_final: false } }

// Final transcript
{ type: "TRANSCRIPT_UPDATE", data: { text: "...", is_final: true } }

// Summary update
{ type: "SUMMARY_UPDATE", data: { summary: "..." } }

// Status
{ type: "STATUS", data: { status: "recording" | "idle" } }
```

---

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

---

## License

MIT License

---


---

