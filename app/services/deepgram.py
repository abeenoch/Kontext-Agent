import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Any, Union

from deepgram import DeepgramClient, AsyncDeepgramClient
from deepgram.core.events import EventType

from app.config import get_settings
from app.logger import get_logger
from app.services.audio import pcm16_to_wav_bytes

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class TranscriptResult:
    """Structured transcript result from Deepgram."""

    text: str
    is_final: bool
    confidence: float
    speaker: Optional[int] = None
    words: list[dict[str, Any]] = field(default_factory=list)


class DeepgramSTTHandler:
    """
    Real-time speech-to-text handler using Deepgram Listen Live v1 WebSocket.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "nova-2",
        language: str = "en",
        sample_rate: int = 16000,
        encoding: str = "linear16",
        enable_interim_results: bool = True,
        enable_punctuation: bool = True,
        enable_diarization: bool = True,
        enable_smart_format: bool = True,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.language = language
        self.sample_rate = sample_rate
        self.encoding = encoding
        self.enable_interim_results = enable_interim_results
        self.enable_punctuation = enable_punctuation
        self.enable_diarization = enable_diarization
        self.enable_smart_format = enable_smart_format

        self._client: Optional[AsyncDeepgramClient] = None
        self._socket: Optional[Any] = None
        self.is_connected: bool = False
        self._task: Optional[asyncio.Task] = None
        self._send_lock = asyncio.Lock()
        self._last_activity_at = 0.0

        self._on_transcript: Optional[Callable[[TranscriptResult], Any]] = None
        self._on_error: Optional[Callable[[str], Any]] = None

    async def connect(
        self,
        on_transcript: Optional[Callable[[TranscriptResult], Any]] = None,
        on_error: Optional[Callable[[str], Any]] = None,
    ) -> bool:
        if not self.api_key:
            logger.error("Deepgram API key not provided")
            return False

        self._on_transcript = on_transcript
        self._on_error = on_error

        try:
            logger.info("Connecting to Deepgram STT (timeout=20s)...")
            self._client = AsyncDeepgramClient(api_key=self.api_key)
            self._task = asyncio.create_task(self._run())
            
            # Wait for connection
            for i in range(200):
                if self.is_connected:
                    logger.info("Deepgram STT connected after %.1fs", (i + 1) * 0.1)
                    return True
                if self._task.done():
                    # Task died early
                    exc = self._task.exception()
                    if exc:
                        raise exc
                    break
                await asyncio.sleep(0.1)
            
            if not self.is_connected:
                logger.error("Deepgram connection timed out after 20s")
                await self.disconnect() 
                return False

            return True

        except Exception as exc:
            logger.error("Failed to connect to Deepgram STT: %s", exc, exc_info=True)
            if self._on_error:
                await self._safe_callback(self._on_error, str(exc))
            return False

    async def _run(self):
        try:
            # Note: SDK path is listen.v1.connect
            # Using parameters from official dashboard sample
            kwargs = {
                "model": self.model,
                "language": self.language,
                "encoding": self.encoding,
                "sample_rate": self.sample_rate,
                "interim_results": self.enable_interim_results,
                "smart_format": self.enable_smart_format,
                "punctuate": self.enable_punctuation,
                "diarize": self.enable_diarization,
                "vad_events": True,
                "utterance_end_ms": 1000,
                "endpointing": 10,
            }

            async with self._client.listen.v1.connect(**kwargs) as socket:
                self._socket = socket
                self._last_activity_at = time.monotonic()
                
                socket.on(EventType.OPEN, self._handle_open)
                socket.on(EventType.MESSAGE, self._handle_message)
                socket.on(EventType.ERROR, self._handle_error)
                socket.on(EventType.CLOSE, self._handle_close)
                
                logger.info("Deepgram STT starting: model=%s", self.model)
                await socket.start_listening()
                
        except asyncio.CancelledError:
            logger.info("Deepgram task cancelled")
        except Exception as exc:
            logger.error("Deepgram background task error: %s", exc, exc_info=True)
            if self._on_error:
                await self._safe_callback(self._on_error, str(exc))
        finally:
            self.is_connected = False
            self._socket = None

    async def send_audio(self, audio_data: bytes) -> bool:
        if not self.is_connected or not self._socket:
            return False

        try:
            #
            async with self._send_lock:
                await self._socket.send_media(audio_data)
                self._last_activity_at = time.monotonic()
            return True
        except Exception as exc:
            logger.error("Error sending audio: %s", exc)
            return False

    async def finish(self) -> None:
        """Tell Deepgram we're done sending audio."""
        if self._socket and self.is_connected:
            try:
                async with self._send_lock:
                    # Deepgram recommends CloseStream to flush and close cleanly.
                    await self._socket._send({"type": "CloseStream"})
                    self._last_activity_at = time.monotonic()
            except Exception as exc:
                logger.warning("CloseStream failed, trying Finalize: %s", exc)
                try:
                    async with self._send_lock:
                        await self._socket._send({"type": "Finalize"})
                        self._last_activity_at = time.monotonic()
                except Exception as inner_exc:
                    logger.error("Error calling finish/finalize: %s", inner_exc)

    async def keepalive(self) -> None:
        """Send a keepalive control frame to prevent idle socket timeout."""
        if self._socket and self.is_connected:
            try:
                async with self._send_lock:
                    await self._socket._send({"type": "KeepAlive"})
                    self._last_activity_at = time.monotonic()
            except Exception as exc:
                logger.debug("Deepgram keepalive failed: %s", exc)

    def seconds_since_last_activity(self) -> float:
        if not self._last_activity_at:
            return 1e9
        return time.monotonic() - self._last_activity_at

    async def disconnect(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        self.is_connected = False
        self._socket = None
        self._client = None

    def _handle_open(self, *args: Any, **_kwargs: Any) -> None:
        logger.info("Deepgram WebSocket opened")
        self.is_connected = True

    async def _handle_message(self, *args: Any, **_kwargs: Any) -> None:
        try:
            result_obj = args[0] if args else None
            if not result_obj:
                logger.debug("Received empty Deepgram message")
                return

            msg_type = getattr(result_obj, "type", "Unknown")
            if msg_type != "Results":
                logger.debug("Deepgram event: %s", msg_type)
                return

            channel = getattr(result_obj, "channel", None)
            if not channel:
                logger.info("Results message missing channel")
                return

            alternatives = getattr(channel, "alternatives", [])
            if not alternatives:
                logger.info("Results message missing alternatives")
                return

            alt = alternatives[0]
            transcript_text = getattr(alt, "transcript", "").strip()
            confidence = getattr(alt, "confidence", 0.0)
            is_final = getattr(result_obj, "is_final", False)
            
            # Avoid heavy INFO logging on interim transcripts in hot path.
            if transcript_text:
                if is_final:
                    logger.info(
                        "Deepgram final utterance chunk (conf=%.3f)", confidence
                    )
                else:
                    logger.debug(
                        "Deepgram interim transcript (conf=%.3f)", confidence
                    )
            else:
                if is_final:
                    logger.debug("Deepgram internal transcript: [EMPTY] (is_final=True, conf=%.3f)", confidence)
                else:
                    logger.debug("Deepgram internal transcript: [EMPTY] (is_final=False)")

            if not transcript_text:
                return

            result = TranscriptResult(
                text=transcript_text,
                is_final=getattr(result_obj, "is_final", False),
                confidence=getattr(alt, "confidence", 0.0),
                speaker=getattr(getattr(alt, "words", [None])[0], "speaker", None) if self.enable_diarization else None,
                words=[
                    {
                        "word": getattr(w, "word", ""),
                        "start": getattr(w, "start", 0.0),
                        "end": getattr(w, "end", 0.0),
                        "speaker": getattr(w, "speaker", None),
                    }
                    for w in getattr(alt, "words", [])
                ]
            )

            if self._on_transcript:
                await self._safe_callback(self._on_transcript, result)
        except Exception as exc:
            logger.error("Error processing Deepgram message: %s", exc, exc_info=True)

    async def _handle_error(self, *args: Any, **_kwargs: Any) -> None:
        error = args[0] if args else "Unknown error"
        logger.error("Deepgram STT error: %s", error)
        if self._on_error:
            await self._safe_callback(self._on_error, str(error))

    def _handle_close(self, *args: Any, **_kwargs: Any) -> None:
        self.is_connected = False

    @staticmethod
    async def _safe_callback(callback: Callable, *args: Any) -> None:
        if asyncio.iscoroutinefunction(callback):
            await callback(*args)
        else:
            callback(*args)


class DeepgramTTSService:
    """
    Text-to-speech service using Deepgram Speak v1 REST API.
    """

    def __init__(self, api_key: str, model: str = "aura-2-thalia-en") -> None:
        self.api_key = api_key
        self.model = model
        self._client: Optional[DeepgramClient] = None

    def _get_client(self) -> DeepgramClient:
        if self._client is None:
            self._client = DeepgramClient(api_key=self.api_key)
        return self._client

    async def synthesize(self, text: str) -> bytes:
        if not text.strip():
            raise ValueError("Empty text")

        try:
            client = self._get_client()
            loop = asyncio.get_running_loop()

            def _call_speak():
                # 
                audio_iterator = client.speak.v1.audio.generate(
                    text=text,
                    model=self.model,
                    encoding="mp3",
                )
                return b"".join(list(audio_iterator))

            return await loop.run_in_executor(None, _call_speak)
        except Exception as exc:
            logger.error("Deepgram TTS error: %s", exc)
            raise RuntimeError(f"TTS failed: {exc}")


class DeepgramFileTranscriber:
    """
    Pre-recorded file transcription using Deepgram Listen v1 REST API.
    """

    def __init__(self, api_key: str, model: str = "nova-2", language: str = "en") -> None:
        self.api_key = api_key
        self.model = model
        self.language = language
        self._client: Optional[DeepgramClient] = None

    def _get_client(self) -> DeepgramClient:
        if self._client is None:
            self._client = DeepgramClient(api_key=self.api_key)
        return self._client

    async def transcribe(
        self,
        audio_data: bytes,
        diarize: bool = False,
        sample_rate: int = 16000,
    ) -> str:
        try:
            client = self._get_client()
            loop = asyncio.get_running_loop()
            
            options = {
                "model": self.model,
                "language": self.language,
                "punctuate": True,
                "diarize": diarize,
            }

            def _call_transcribe():
                # Browser voice uploads are raw PCM16; wrap in WAV first.
                wav_data = pcm16_to_wav_bytes(audio_data, sample_rate=sample_rate)

                # 
                response = client.listen.v1.media.transcribe_file(
                    request=wav_data,
                    **options
                )
                return response.results.channels[0].alternatives[0].transcript

            return await loop.run_in_executor(None, _call_transcribe)
        except Exception as exc:
            logger.error("File transcription error: %s", exc)
            raise RuntimeError(f"Transcription failed: {exc}")


_tts_service = None
_file_transcriber = None

def get_tts_service() -> DeepgramTTSService:
    global _tts_service
    if _tts_service is None:
        _tts_service = DeepgramTTSService(
            api_key=settings.deepgram_api_key,
            model=settings.deepgram_tts_model,
        )
    return _tts_service

def get_file_transcriber() -> DeepgramFileTranscriber:
    global _file_transcriber
    if _file_transcriber is None:
        _file_transcriber = DeepgramFileTranscriber(
            api_key=settings.deepgram_api_key,
            model=settings.deepgram_model,
            language=settings.deepgram_language,
        )
    return _file_transcriber
