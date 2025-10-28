import asyncio
import sounddevice as sd
import numpy as np
import tempfile
import wave
from faster_whisper import WhisperModel
from app.services.llm_agent import query_llm
from app.services.voice_agent import speak
import io
import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel

model = WhisperModel("base")

async def handle_voice_stream(ws):
    await ws.accept()
    await ws.send_text("Voice stream connected. Speak now!")

    # open continuous recording
    samplerate = 16000
    blocksize = 4096
    duration = 0.5  # 
    recording = True

    try:
        with sd.InputStream(samplerate=samplerate, channels=1, blocksize=blocksize) as stream:
            buffer = np.array([], dtype=np.float32)

            while recording:
                data, _ = stream.read(blocksize)
                buffer = np.concatenate((buffer, data.flatten()))

                # if buffer large enough -> process chunk
                if len(buffer) > samplerate * duration:
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                        with wave.open(tmp.name, "wb") as wf:
                            wf.setnchannels(1)
                            wf.setsampwidth(2)
                            wf.setframerate(samplerate)
                            wf.writeframes((buffer * 32767).astype(np.int16).tobytes())
                        filename = tmp.name

                    # Transcribe current chunk
                    segments, _ = model.transcribe(filename)
                    text = " ".join([seg.text for seg in segments])

                    if text.strip():
                        await ws.send_text(f"You said: {text}")
                        # Query LLM
                        llm_resp = query_llm(text)
                        speak(llm_resp)
                        await ws.send_text(f" {llm_resp}")

                    buffer = np.array([], dtype=np.float32)
                await asyncio.sleep(0.1)

    except Exception as e:
        await ws.send_text(f" Error: {e}")
    finally:
        await ws.close()




def handle_audio_chunk(audio_bytes: bytes):
    # Convert raw bytes → wav → numpy array
    try:
        data, samplerate = sf.read(io.BytesIO(audio_bytes))
        segments, _ = model.transcribe(data)
        text = " ".join([seg.text for seg in segments])
        return text
    except Exception as e:
        print("Error processing audio chunk:", e)
        return None
