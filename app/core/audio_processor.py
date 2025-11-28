import numpy as np
import logging
from typing import Tuple, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class AudioBuffer:
    """
    Manages audio buffering for streaming transcription.
    
    Key features:
    - Accumulates PCM audio chunks
    - Tracks processed offset to avoid reprocessing
    - Provides windows of audio for Whisper
    """
    
    def __init__(self):
        self.buffer = bytearray()
        self.processed_offset = 0
        self.sample_rate = settings.SAMPLE_RATE
        self.window_size_bytes = settings.SAMPLE_RATE * settings.TRANSCRIPTION_WINDOW_SEC * 2  # S16LE = 2 bytes/sample
        
    def add_chunk(self, chunk_data: bytes) -> None:
        """Add audio chunk to buffer."""
        self.buffer.extend(chunk_data)
        logger.debug(f"Buffer size: {len(self.buffer)} bytes, processed: {self.processed_offset}")
    
    def get_unprocessed_audio(self) -> Optional[Tuple[np.ndarray, int]]:
        """
        Get unprocessed audio as numpy array.
        
        Returns:
            Tuple of (audio_array, bytes_to_process) or None if insufficient data
        """
        available = len(self.buffer) - self.processed_offset
        
        # Need at least 10 seconds of audio for good transcription context
        from app.config import settings as cfg
        min_bytes = cfg.SAMPLE_RATE * cfg.MIN_AUDIO_DURATION_SEC * 2 if hasattr(cfg, 'MIN_AUDIO_DURATION_SEC') else self.sample_rate * 10 * 2
        
        # DEBUG
        available_secs = available / (self.sample_rate * 2)
        min_secs = min_bytes / (self.sample_rate * 2)
        
        if available < min_bytes:
            logger.debug(f"[BUFFER] Insufficient audio: {available_secs:.1f}s available < {min_secs:.1f}s minimum required")
            return None
        
        # Process up to window size (60 seconds for better context)
        bytes_to_process = min(available, self.window_size_bytes)
        window_secs = bytes_to_process / (self.sample_rate * 2)
        
        # Extract audio chunk
        chunk = self.buffer[self.processed_offset:self.processed_offset + bytes_to_process]
        
        # Convert to numpy array (int16 -> float32 normalized)
        audio_np = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
        
        # AUTO-NORMALIZE if audio is too quiet (fallback if browser didn't normalize)
        max_abs = np.max(np.abs(audio_np)) if len(audio_np) > 0 else 0
        if max_abs > 0 and max_abs < 0.1:  # Quieter than -20dB
            old_max = max_abs
            audio_np = audio_np * (0.5 / max_abs)  # Normalize to 0.5 amplitude (~-26dB, safe margin)
            logger.info(f"[BUFFER] Auto-normalized: {old_max:.4f} → 0.5 ({window_secs:.1f}s)")
        
        logger.debug(f"[BUFFER] Returning window: {window_secs:.1f}s ({bytes_to_process} bytes) from {available_secs:.1f}s available")
        return audio_np, bytes_to_process
    
    def mark_processed(self, num_bytes: int) -> None:
        """Mark bytes as processed."""
        self.processed_offset += num_bytes
        logger.debug(f"Marked {num_bytes} bytes as processed. New offset: {self.processed_offset}")
    
    def get_remaining_audio(self) -> Optional[np.ndarray]:
        """Get all remaining unprocessed audio."""
        if self.processed_offset >= len(self.buffer):
            return None
        
        chunk = self.buffer[self.processed_offset:]
        if len(chunk) == 0:
            return None
        
        return np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
    
    def clear(self) -> None:
        """Clear buffer and reset offset."""
        self.buffer = bytearray()
        self.processed_offset = 0
    
    @property
    def total_duration_seconds(self) -> float:
        """Calculate total audio duration in seconds."""
        return len(self.buffer) / (self.sample_rate * 2)  # 2 bytes per sample
    
    @property
    def unprocessed_duration_seconds(self) -> float:
        """Calculate unprocessed audio duration in seconds."""
        unprocessed_bytes = len(self.buffer) - self.processed_offset
        return unprocessed_bytes / (self.sample_rate * 2)


class AudioValidator:
    """Validates incoming audio chunks."""
    
    @staticmethod
    def validate_pcm_chunk(chunk_data: bytes, expected_chunk_size: int = None) -> bool:
        """
        Validate PCM audio chunk.
        
        Args:
            chunk_data: Raw PCM bytes
            expected_chunk_size: Expected chunk size (optional, warning only if mismatched)
        
        Returns:
            True if valid
        """
        if not chunk_data:
            logger.debug("Empty audio chunk received")
            return False
        
        # Check if size is even (S16LE = 2 bytes per sample)
        if len(chunk_data) % 2 != 0:
            logger.warning(f"Invalid PCM chunk size: {len(chunk_data)} (not even)")
            return False
        
        # Check expected size if provided - only debug level since chunk size can vary
        if expected_chunk_size and len(chunk_data) != expected_chunk_size:
            logger.debug(f"Chunk size: {len(chunk_data)} bytes (expected: {expected_chunk_size})")
        
        return True
    
    @staticmethod
    def validate_audio_array(audio_np: np.ndarray) -> bool:
        """Validate numpy audio array."""
        if audio_np is None or len(audio_np) == 0:
            return False
        
        # Check for invalid values
        if np.any(np.isnan(audio_np)) or np.any(np.isinf(audio_np)):
            logger.warning("Audio contains NaN or Inf values")
            return False
        
        # Check range (-1.0 to 1.0 for normalized audio)
        if np.max(np.abs(audio_np)) > 1.5:  # Allow some headroom
            logger.warning(f"Audio values out of range: max={np.max(np.abs(audio_np))}")
        
        return True