import sounddevice as sounddevice
import numpy as np
import tempfile
import subprocess
from faster_whisper import WhisperModel
import pyttsx3
import sounddevice as sd
from app.services.llm_agent import query_llm
import soundfile as sf
import os
import time

def record_audio(duration=5, samplerate=16000, filename="temp_audio.wav", device=1):
    """Record audio and ensure file is written before returning."""
    try:
        print(f"Recording {duration}s of audio using device {device}...")
        sd.default.device = device
        audio = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype='float32')
        sd.wait()  # ensure recording completes
        audio = np.squeeze(audio)
        sf.write(filename, audio, samplerate)

        # ensure file is really saved before returning
        timeout = 2
        for _ in range(timeout * 10):  # wait up to 2 seconds
            if os.path.exists(filename) and os.path.getsize(filename) > 1000:
                print(f"Saved recording to {filename} ({os.path.getsize(filename)} bytes)")
                return filename
            time.sleep(0.1)
        raise FileNotFoundError(f"File {filename} not found after recording.")
    except Exception as e:
        print(f"Recording failed: {e}")
        raise


model = WhisperModel("base")

def transcribe_audio():
    filename = record_audio(duration=5)
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Audio file not found: {filename}")
    print(f"🔊 Transcribing {filename} ...")
    segments, info = model.transcribe(filename)
    text = " ".join([seg.text for seg in segments])
    print(f"Transcribed Text: {text}")
    return text

def voice_chat():
    """Record voice, transcribe, and generate LLM reply."""
    audio_path = record_audio(5)
    user_text = transcribe_audio(audio_path)
    response = query_llm(f"User said: {user_text}. Reply naturally and helpfully.")
    return {"transcript": user_text, "response": response}

tts_engine = pyttsx3.init()
tts_engine.setProperty('rate', 180)

def speak(text: str):
    print(f"Speaking: {text}")
    tts_engine.say(text)
    tts_engine.runAndWait()