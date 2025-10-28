import io
import pyttsx3

def synthesize(text: str) -> bytes:
    """Convert text to speech and return raw WAV bytes."""
    engine = pyttsx3.init()
    # Save speech to a temporary in-memory file
    audio_buffer = io.BytesIO()
    engine.save_to_file(text, "temp_tts.wav")
    engine.runAndWait()
    with open("temp_tts.wav", "rb") as f:
        return f.read()
