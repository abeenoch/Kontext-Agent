import io
import base64
import numpy as np
import soundfile as sf
import subprocess
from faster_whisper import WhisperModel
from app.services.llm_agent import query_llm
from app.services.tts_engine import synthesize

model = WhisperModel("base", device="cpu")


async def transcribe_audio_stream(audio_base64: str) -> str:
    """
    Receives base64 WebM audio chunks, converts to WAV via ffmpeg, transcribes with Whisper.
    """
    try:
        # Decode base64 → bytes → temp.webm
        audio_data = base64.b64decode(audio_base64)
        webm_path = "temp_stream.webm"
        wav_path = "temp_stream.wav"

        with open(webm_path, "wb") as f:
            f.write(audio_data)

        # Convert WebM (Opus) → WAV (PCM) using ffmpeg
        cmd = [
            "ffmpeg",
            "-y",  # overwrite
            "-i", webm_path,
            "-ar", "16000",  # resample to 16kHz
            "-ac", "1",      # mono
            wav_path,
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

        #  Load with soundfile
        audio, sr = sf.read(wav_path)
        if sr != 16000:
            print(f"Unexpected sample rate: {sr}")

        # Transcribe
        segments, _ = model.transcribe(wav_path)
        text = " ".join([seg.text for seg in segments])
        return text.strip()

    except Exception as e:
        print(f"Error in transcribe_audio_stream: {e}")
        return ""


async def generate_llm_reply(text: str) -> str:
    """Query the LLM and return reply text."""
    return query_llm(text)


async def synthesize_speech(text: str) -> str:
    """Convert LLM text to speech (base64)."""
    audio_bytes = synthesize(text)
    return base64.b64encode(audio_bytes).decode("utf-8")
