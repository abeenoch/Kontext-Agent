# app/utils/audio_utils.py
import base64
import subprocess
import tempfile
import os
from io import BytesIO

import soundfile as sf
import numpy as np

FFMPEG_CMD = os.environ.get("FFMPEG_CMD", "ffmpeg")  


def decode_webm_base64_to_wav_bytes(data_b64: str) -> bytes:
    """
    More robust decode: base64 → temp.webm → ffmpeg → wav bytes.
    """

    webm_data = base64.b64decode(data_b64)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as f_in:
        f_in.write(webm_data)
        f_in.flush()
        wav_path = f_in.name.replace(".webm", ".wav")

        # Explicitly tell ffmpeg to decode opus streams safely
        cmd = [
            "ffmpeg", "-y",
            "-i", f_in.name,
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            wav_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg conversion failed: {result.stderr}")

        with open(wav_path, "rb") as f_out:
            return f_out.read()


def append_wav_chunk(target_path: str, wav_bytes: bytes):
    """
    Append `wav_bytes` (a valid WAV file's bytes) to target_path (WAV).
    If target_path doesn't exist it will be created from wav_bytes.
    If it exists, this reads both, concatenates PCM frames and re-writes a single WAV.
    Uses soundfile (pysoundfile) to read and write.
    """
    # read incoming bytes
    incoming_io = BytesIO(wav_bytes)
    data, sr = sf.read(incoming_io, dtype='float32')
    # ensure 1D (mono) or 2D (frames, channels)
    if data.ndim > 1:
        # convert to mono by averaging channels if necessary
        data = np.mean(data, axis=1)

    if not os.path.exists(target_path):
        # simply write incoming chunk
        sf.write(target_path, data, sr, format="WAV")
        return

    # if target exists, read existing and concatenate
    existing_data, existing_sr = sf.read(target_path, dtype='float32')
    if existing_data.ndim > 1:
        existing_data = np.mean(existing_data, axis=1)

    if existing_sr != sr:
        # resampling would be necessary - for now raise to avoid silent corruption
        raise RuntimeError(f"Sample rate mismatch: existing {existing_sr} vs incoming {sr}")

    new = np.concatenate([existing_data, data], axis=0)
    sf.write(target_path, new, sr, format="WAV")
