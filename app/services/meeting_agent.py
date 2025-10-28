import os
import time
import tempfile
import threading
import queue
from typing import Optional, Dict, Any, List
import sounddevice as sd
import soundfile as sf
import requests
import asyncio

from app.services.rag_pipeline import retrieve_relevant_docs
from app.services.llm_agent import query_llm

# Environment / config
RECORDINGS_DIR = os.getenv("RECORDINGS_DIR", "./recordings")
os.makedirs(RECORDINGS_DIR, exist_ok=True)

BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL", "")

# 
_sessions: Dict[str, Dict[str, Any]] = {}
# Each session holds: {"thread": Thread, "stop_event": Event, "file_path": str, "samplerate": int, "channels": int}

def _make_filename(user_id: str):
    ts = int(time.time())
    safe = user_id.replace(" ", "_")
    return os.path.join(RECORDINGS_DIR, f"{safe}_{ts}.wav")


def start_recording(user_id: str, samplerate: int = 16000, channels: int = 1) -> str:
    """
    Start a background recording session for user_id.
    Returns the file path that will be written to.
    """
    if user_id in _sessions:
        raise RuntimeError("Recording already in progress for this user")

    file_path = _make_filename(user_id)
    stop_event = threading.Event()
    q = queue.Queue(maxsize=100)

    def callback(indata, frames, time_info, status):
        if status:
            print(f"[record] status: {status}")
        try:
            q.put_nowait(indata.copy())
        except queue.Full:
            # drop if queue is full
            pass

    def writer_thread():
        # Write as 16-bit PCM WAV
        with sf.SoundFile(file_path, mode='w', samplerate=samplerate, channels=channels, subtype='PCM_16') as f:
            with sd.InputStream(samplerate=samplerate, channels=channels, callback=callback):
                while not stop_event.is_set():
                    try:
                        data = q.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    f.write(data)
                # flush remaining
                while not q.empty():
                    f.write(q.get())

    thread = threading.Thread(target=writer_thread, daemon=True)
    _sessions[user_id] = {"thread": thread, "stop_event": stop_event, "file_path": file_path, "samplerate": samplerate, "channels": channels}
    thread.start()
    return file_path


def stop_recording(user_id: str) -> Optional[str]:
    """
    Stop recording session for user_id. Returns path to saved .wav file or None.
    """
    s = _sessions.get(user_id)
    if not s:
        return None
    s["stop_event"].set()
    s["thread"].join(timeout=5)
    path = s["file_path"]
    # cleanup session
    del _sessions[user_id]
    return path


# 
def transcribe_file_whisper(audio_path: str, model_size: str = "small") -> str:
    """
    Transcribe audio using faster-whisper local model.
    Requires `faster-whisper` to be installed and model files will be downloaded on first run.
    """
    try:
        from faster_whisper import WhisperModel
    except Exception as e:
        raise RuntimeError("faster-whisper is not installed. pip install faster-whisper") from e

    model = WhisperModel(model_size, device="cpu", compute_type="int8")  # change device to "cuda" if available
    segments, info = model.transcribe(audio_path, beam_size=5)
    text = " ".join([seg.text for seg in segments])
    return text


async def transcribe_meeting(audio_path: str, model_size: str = "small") -> str:
    # run blocking transcription in thread
    return await asyncio.to_thread(transcribe_file_whisper, audio_path, model_size)


# 
async def summarize_meeting(user_id: str, transcript: str, include_documents: bool = True) -> Dict[str, Any]:
    """
    Build a prompt combining transcript + optionally retrieved docs and call the LLM.
    Returns: {"summary": str, "action_items": str, "full_response": str}
    """
    # optionally retrieve related docs for user context
    retrieved = []
    if include_documents:
        try:
            # retrieve relevant docs (sync) - retrieval uses embeddings so keep it sync
            retrieved = retrieve_relevant_docs(user_id, transcript, k=4)
        except Exception as e:
            print("[meeting_agent] retrieve_relevant_docs failed:", e)
            retrieved = []

    context_text = "\n\n".join([d["content"] for d in retrieved]) if retrieved else ""
    prompt = f"""
You are a meeting assistant. The following is a transcribed meeting. Produce:
1) An executive summary (2-4 sentences)
2) A bullet list of action items (who/what/when if present)
3) Any key decisions reached

Include relevant context from the user's documents when helpful.

DOCUMENT CONTEXT:
{context_text}

TRANSCRIPT:
{transcript}

Respond in JSON with keys: summary, action_items, decisions, full_text
"""
    # query_llm is synchronous (uses requests). run in thread
    raw = await asyncio.to_thread(query_llm, prompt)
    # Try to parse if LLM returned JSON; if not, wrap
    try:
        import json
        parsed = json.loads(raw)
        return parsed
    except Exception:
        return {"summary": raw, "action_items": "", "decisions": "", "full_text": raw}


# 
def email_summary_brevo(subject: str, html_content: str, to_emails: List[str]) -> Dict[str, Any]:
    """
    Send summary via Brevo (SendinBlue) SMTP transactional API.
    Requires BREVO_API_KEY and BREVO_SENDER_EMAIL set in environment.
    """
    if not BREVO_API_KEY or not BREVO_SENDER_EMAIL:
        raise RuntimeError("Brevo API key or sender email not configured in env (BREVO_API_KEY/BREVO_SENDER_EMAIL)")

    url = "https://api.brevo.com/v3/smtp/email"
    payload = {
        "sender": {"email": BREVO_SENDER_EMAIL},
        "to": [{"email": e} for e in to_emails],
        "subject": subject,
        "htmlContent": html_content
    }
    headers = {"api-key": BREVO_API_KEY, "Content-Type": "application/json"}
    r = requests.post(url, json=payload, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()
