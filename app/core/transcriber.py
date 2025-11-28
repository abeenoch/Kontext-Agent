import asyncio
import numpy as np
import logging
from typing import Optional
from faster_whisper import WhisperModel

from app.config import settings

logger = logging.getLogger(__name__)


class Transcriber:
    """
    Async wrapper for Whisper transcription.
    
    Uses faster-whisper for efficient CPU/GPU inference.
    """
    
    def __init__(self):
        self.model_name = settings.WHISPER_MODEL
        self.device = settings.WHISPER_DEVICE
        self.compute_type = settings.WHISPER_COMPUTE_TYPE
        self.model: Optional[WhisperModel] = None
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """Initialize Whisper model (lazy loading)."""
        if self.model is not None:
            return
        
        logger.info(f"Loading Whisper model: {self.model_name} on {self.device}")
        
        # Load model in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        self.model = await loop.run_in_executor(
            None,
            lambda: WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
                num_workers=1
            )
        )
        
        logger.info("Whisper model loaded successfully")
    
    async def transcribe(self, audio_np: np.ndarray, language: str = "en") -> str:
        """
        Transcribe audio array.
        
        Args:
            audio_np: Normalized float32 audio array
            language: Language code (default: en)
        
        Returns:
            Transcribed text
        """
        await self.initialize()
        
        if audio_np is None or len(audio_np) == 0:
            return ""
        
        # DEBUG: Check amplitude before transcription
        max_amp = np.max(np.abs(audio_np))
        audio_duration = len(audio_np) / settings.SAMPLE_RATE
        logger.info(f"Transcribe: {audio_duration:.1f}s audio, max_amp={max_amp:.4f}, samples={len(audio_np)}")
        
        if max_amp < 0.01:
            logger.warning(f"AUDIO TOO QUIET: max_amp={max_amp:.4f} (should be ~0.5). Likely hallucination incoming.")
        
        # Run transcription in thread pool
        async with self._lock:  # Prevent concurrent transcriptions
            loop = asyncio.get_event_loop()
            try:
                segments, info = await loop.run_in_executor(
                    None,
                    lambda: self.model.transcribe(
                        audio_np,
                        language=language,
                        beam_size=5,  # Better accuracy (was 1 for speed)
                        best_of=5,  # Return best of 5 decoding attempts
                        temperature=0.0,  # Deterministic
                        vad_filter=False  # Disable VAD for streaming chunks to avoid false negatives
                    )
                )
                
                # Extract text from segments
                text = " ".join([segment.text.strip() for segment in segments])
                
                logger.info(f"Transcribed {audio_duration:.2f}s audio -> {len(text)} chars: {text[:100]}")
                
                return text.strip()
                
            except Exception as e:
                logger.error(f"Transcription error: {e}", exc_info=True)
                return ""
    
    async def transcribe_final(self, audio_np: np.ndarray, language: str = "en") -> str:
        """
        Transcribe with higher quality settings for final transcription.
        
        Args:
            audio_np: Normalized float32 audio array
            language: Language code
        
        Returns:
            Transcribed text
        """
        await self.initialize()
        
        if audio_np is None or len(audio_np) == 0:
            return ""
        
        async with self._lock:
            loop = asyncio.get_event_loop()
            try:
                segments, info = await loop.run_in_executor(
                    None,
                    lambda: self.model.transcribe(
                        audio_np,
                        language=language,
                        beam_size=5,  # Higher quality
                        best_of=5,
                        temperature=0.0,
                        vad_filter=False
                    )
                )
                
                text = " ".join([segment.text.strip() for segment in segments])
                
                logger.info(f"Final transcription: {len(audio_np)/settings.SAMPLE_RATE:.2f}s audio -> {len(text)} chars")
                
                return text.strip()
                
            except Exception as e:
                logger.error(f"Final transcription error: {e}", exc_info=True)
                return ""



transcriber = Transcriber()