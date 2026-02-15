import base64
import io
import struct
import wave
from typing import Optional

from app.logger import get_logger

logger = get_logger(__name__)


def process_browser_audio(base64_data: str) -> Optional[bytes]:
    """
    Decode base64-encoded PCM16 audio from browser.

    Frontend already converted Float32 to Int16 (PCM16).
    We just decode the base64 string to raw bytes.
    """
    try:
        pcm_bytes = base64.b64decode(base64_data)

        if not hasattr(process_browser_audio, "_first_logged"):
            num_samples = min(10, len(pcm_bytes) // 2)
            if num_samples > 0:
                samples = struct.unpack("<" + "h" * num_samples, pcm_bytes[: num_samples * 2])

                logger.info("=" * 60)
                logger.info("AUDIO PROCESSING - First chunk")
                logger.info("  Base64 length: %d chars", len(base64_data))
                logger.info("  PCM16 bytes: %d", len(pcm_bytes))
                logger.info("  Samples: %d", len(pcm_bytes) // 2)
                logger.info("  First 10: %s", samples)
                logger.info("  Range: [%d, %d]", min(samples), max(samples))

                if -32768 <= min(samples) <= max(samples) <= 32767:
                    logger.info("Valid PCM16 format")
                else:
                    logger.warning("Invalid PCM16 range")
                logger.info("=" * 60)

            process_browser_audio._first_logged = True

        return pcm_bytes

    except Exception as exc:
        logger.error("Error decoding audio: %s", exc)
        return None


def pcm16_to_wav_bytes(
    pcm_bytes: bytes,
    sample_rate: int = 16000,
    channels: int = 1,
) -> bytes:
    """Wrap raw PCM16 bytes in a WAV container for prerecorded STT APIs."""
    if not pcm_bytes:
        return b""

    with io.BytesIO() as buffer:
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_bytes)
        return buffer.getvalue()
