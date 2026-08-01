import asyncio
import base64

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth import get_current_user_ws
from app.services.deepgram import DeepgramSTTHandler, TranscriptResult, get_tts_service
from app.services.audio import process_browser_audio
from app.services.llm_agent import query_llm
from app.services.chat_memory import add_message, get_recent_history
from app.prompts import VOICE_CHAT_SYSTEM_PROMPT, build_voice_chat_user
from app.config import get_settings
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/voice-chat", tags=["Voice Chat"])


@router.websocket("/ws")
async def voice_chat_websocket(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time voice chat.

    Protocol:
    - Client sends base64-encoded PCM audio chunks.
    - Server transcribes via Deepgram, generates LLM response, synthesizes TTS.
    - Server sends back JSON messages with transcript, LLM response, and audio.
    """
    user_id = await get_current_user_ws(websocket)
    await websocket.accept()
    logger.info("Voice chat session started for user")
    deepgram_handler: DeepgramSTTHandler | None = None
    conversation_history: list[dict[str, str]] = []
    keepalive_task: asyncio.Task | None = None

    try:
        # Load recent chat history
        try:
            conversation_history = await get_recent_history(user_id)
        except Exception:
            pass

        # 

        async def on_transcript(result: TranscriptResult) -> None:
            if not result.is_final:
                await websocket.send_json(
                    {"type": "interim_transcript", "text": result.text}
                )
                return

            logger.info("Voice chat transcription: %s", result.text)

            await websocket.send_json(
                {"type": "final_transcript", "text": result.text}
            )

            # Build prompt with conversation context
            history_text = ""
            for msg in conversation_history[-6:]:
                role_label = "User" if msg["role"] == "user" else "Assistant"
                history_text += f"{role_label}: {msg['content']}\n"

            user_prompt = build_voice_chat_user(history_text, result.text)

            try:
                llm_response = await query_llm(
                    user_prompt, system_prompt=VOICE_CHAT_SYSTEM_PROMPT
                )

                # Save to memory
                conversation_history.append({"role": "user", "content": result.text})
                conversation_history.append(
                    {"role": "assistant", "content": llm_response}
                )
                await add_message(user_id, "user", result.text)
                await add_message(user_id, "assistant", llm_response)

                await websocket.send_json(
                    {"type": "llm_response", "text": llm_response}
                )

                # Synthesize TTS
                try:
                    tts = get_tts_service()
                    audio_bytes = await tts.synthesize(llm_response)
                    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                    await websocket.send_json(
                        {"type": "tts_audio", "audio": audio_b64, "format": "mp3"}
                    )
                except Exception as exc:
                    logger.error("TTS error: %s", exc)
                    await websocket.send_json(
                        {"type": "error", "message": "TTS synthesis failed"}
                    )

            except Exception as exc:
                logger.error("LLM error in voice chat: %s", exc, exc_info=True)
                await websocket.send_json(
                    {"type": "error", "message": "Failed to generate response"}
                )

        async def on_error(error: str) -> None:
            logger.error("Deepgram voice chat error: %s", error)
            await websocket.send_json(
                {"type": "error", "message": f"Transcription error: {error}"}
            )

        #connect to Deepgram

        if not settings.deepgram_api_key:
            await websocket.send_json(
                {"type": "error", "message": "Deepgram API key not configured"}
            )
            return

        deepgram_handler = DeepgramSTTHandler(
            api_key=settings.deepgram_api_key,
            model=settings.deepgram_model,
            language=settings.deepgram_language,
            enable_interim_results=True,
            enable_punctuation=True,
            enable_diarization=False,  # single-speaker voice chat
            enable_smart_format=True,
        )

        if not await deepgram_handler.connect(
            on_transcript=on_transcript, on_error=on_error
        ):
            await websocket.send_json(
                {"type": "error", "message": "Failed to connect to Deepgram"}
            )
            return

        await websocket.send_json(
            {"type": "status", "message": "Connected. Start speaking."}
        )

        async def deepgram_keepalive() -> None:
            while True:
                await asyncio.sleep(3)
                if deepgram_handler and deepgram_handler.is_connected:
                    if deepgram_handler.seconds_since_last_activity() >= 2.0:
                        await deepgram_handler.keepalive()

        keepalive_task = asyncio.create_task(deepgram_keepalive())

        #main loop 

        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(), timeout=settings.websocket_timeout
                )
            except asyncio.TimeoutError:
                logger.info("Voice chat timeout for user %s", user_id)
                break

            if data == "STOP":
                logger.info("Voice chat ended by user: %s", user_id)
                break

            # Process incoming audio
            try:
                pcm_data = process_browser_audio(data)
                if pcm_data:
                    await deepgram_handler.send_audio(pcm_data)
            except Exception as exc:
                logger.error("Audio processing error: %s", exc)

    except WebSocketDisconnect:
        logger.info("Voice chat client disconnected: %s", user_id)
    except Exception as exc:
        logger.error("Voice chat error: %s", exc, exc_info=True)
    finally:
        if keepalive_task:
            keepalive_task.cancel()
            try:
                await keepalive_task
            except asyncio.CancelledError:
                pass
        if deepgram_handler:
            await deepgram_handler.disconnect()
        logger.info("Voice chat session ended: %s", user_id)
