import os
import tempfile
import base64
from typing import Optional
import re
from app.services.integrations_service import send_meeting_summary_email
from app.utils.audio_utils import decode_webm_base64_to_wav_bytes
from app.services.llm_agent import query_llm
from app.services.tts_engine import synthesize  
from faster_whisper import WhisperModel

# load model once (example)
MODEL = WhisperModel("small", device="cpu", compute_type="float32")  
async def transcribe_audio_stream(audio_base64: str) -> str:
    """Decode WebM → WAV → text using Whisper"""
    try:
        print("[DEBUG] Starting transcription...")

        # Decode webm audio from frontend
        wav_bytes = decode_webm_base64_to_wav_bytes(audio_base64)
        print(f"[DEBUG] Decoded {len(wav_bytes)} bytes of WAV audio")

        # Write to temp file for Whisper
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(wav_bytes)
            tmp_path = tmp.name

        # Run Whisper transcription
        segments, info = MODEL.transcribe(
            tmp_path,
            beam_size=5,
            language="en",
            vad_filter=True,
        )

        full_text = " ".join([seg.text.strip() for seg in segments])
        print(f"[DEBUG] Whisper output: {full_text}")

        os.remove(tmp_path)
        return full_text.strip() if full_text else "[No speech detected]"

    except Exception as e:
        print(f"[ERROR in transcribe_audio_stream]: {e}")
        return ""

async def generate_llm_reply(text: str) -> str:
    if not text:
        return ""
    # query llm agent 
    return query_llm(text)


async def synthesize_speech(text: str) -> str:
    """
    Convert LLM text to speech bytes and return base64 string for websocket json.
    `synthesize` should return raw bytes (wav) — adapt as needed.
    """
    if not text:
        return ""
    audio_bytes = synthesize(text)  
    return base64.b64encode(audio_bytes).decode("utf-8")

def extract_emails_from_text(text: str):
    """Extract all email addresses from a text string."""
    pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    return re.findall(pattern, text)
