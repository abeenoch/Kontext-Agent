"""
Meeting route -- real-time transcription with AI summaries.

Provides:
- WebSocket /meeting/ws for live PCM streaming to Deepgram
- REST endpoints for meeting history, transcripts, summaries, and post-chat
"""

import os
import asyncio
import json
import re
import hashlib
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from app.services.deepgram import DeepgramSTTHandler, TranscriptResult
from app.services.audio import process_browser_audio
from app.services.llm_agent import query_llm
from app.services.summarizer import (
    summarize_periodically,
    compute_initial_periodic_delay_seconds,
)
from app.services.integrations_service import (
    send_meeting_summary_email,
    push_meeting_summary_to_notion,
)
from app.services.chat_memory import (
    save_meeting_chunk,
    save_meeting_summary,
    get_meeting_summary,
    get_meeting_transcript,
    list_meetings,
)
from app.auth import get_current_user, get_current_user_ws
from app.config import get_settings
from app.logger import get_logger
from app.validators import validate_meeting_id

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/meeting", tags=["Meeting"])

os.makedirs(settings.transcripts_dir, exist_ok=True)


def _fallback_summary_from_transcript(transcript: str) -> str:
    """Build a deterministic fallback summary when LLM is unavailable."""
    lines = [line.strip() for line in transcript.splitlines() if line.strip()]
    content_lines = [line for line in lines if not line.startswith("Meeting Transcript") and not line.startswith("=")]
    excerpt = content_lines[-12:] if content_lines else []

    body = "\n".join(f"- {line}" for line in excerpt) if excerpt else "- No transcript content captured."
    return (
        "## Meeting Summary\n"
        "Automatic fallback summary was used because the LLM provider is unavailable.\n\n"
        "### Transcript Highlights\n"
        f"{body}\n"
    )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class MeetingChatRequest(BaseModel):
    """Post-meeting chat request."""
    query: str
    voice_audio: str | None = None  # optional base64 PCM for voice input


class MeetingChatResponse(BaseModel):
    """Post-meeting chat response."""
    response: str
    audio: str | None = None  # optional base64 TTS audio


class MeetingSummaryResponse(BaseModel):
    """Meeting summary response."""
    meeting_id: str
    summary: str | None


class MeetingTranscriptResponse(BaseModel):
    """Meeting transcript response."""
    meeting_id: str
    transcript: str


class MeetingListItem(BaseModel):
    """Single meeting in the list."""
    meeting_id: str
    started_at: str | None
    has_summary: bool


# ---------------------------------------------------------------------------
# WebSocket -- live meeting transcription
# ---------------------------------------------------------------------------


@router.websocket("/ws")
async def meeting_websocket(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time meeting transcription with Deepgram."""
    user_id = await get_current_user_ws(websocket)

    requested_meeting_id = websocket.query_params.get("meeting_id")
    if requested_meeting_id:
        try:
            meeting_id = validate_meeting_id(requested_meeting_id)
        except HTTPException:
            await websocket.close(code=1008)
            return
    else:
        meeting_id = os.urandom(16).hex()

    await websocket.accept()
    logger.info("Meeting started: %s", meeting_id)

    user_scope = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]

    transcript_path = os.path.join(
        settings.transcripts_dir, f"transcript_{user_scope}_{meeting_id}.txt"
    )
    summary_path = os.path.join(
        settings.transcripts_dir, f"summary_{user_scope}_{meeting_id}.txt"
    )

    if not os.path.exists(transcript_path):
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(
                f"Meeting Transcript - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            f.write("=" * 60 + "\n\n")

    deepgram_handler: DeepgramSTTHandler | None = None
    meeting_active = True
    summary_task: asyncio.Task | None = None
    keepalive_task: asyncio.Task | None = None
    current_sample_rate = 16000
    stt_needs_reconnect = False
    reconnect_attempting = False

    async def safe_send_json(payload: dict) -> None:
        try:
            await websocket.send_json(payload)
        except Exception as exc:
            logger.debug("Skipping websocket send (likely disconnected): %s", exc)

    def build_stt_handler(sample_rate: int) -> DeepgramSTTHandler:
        return DeepgramSTTHandler(
            api_key=settings.deepgram_api_key,
            model=settings.deepgram_model,
            language=settings.deepgram_language,
            sample_rate=sample_rate,
            encoding="linear16",
            enable_interim_results=True,
            enable_punctuation=True,
            enable_diarization=True,
            enable_smart_format=True,
        )

    try:
        # -- transcript callback --------------------------------------------------

        async def on_transcript(result: TranscriptResult) -> None:
            if not result.is_final:
                await safe_send_json({"type": "interim", "text": result.text})
                return

            logger.info(
                "Final utterance captured for meeting=%s speaker=%s",
                meeting_id,
                result.speaker,
            )

            transcript_line = (
                f"[Speaker {result.speaker}] {result.text}"
                if result.speaker is not None
                else result.text
            )

            timestamp = datetime.now().strftime("%H:%M:%S")
            with open(transcript_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {transcript_line}\n")

            try:
                await save_meeting_chunk(user_id, meeting_id, transcript_line)
            except Exception as exc:
                logger.warning("Failed to save chunk to DB: %s", exc)

            await safe_send_json(
                {
                    "type": "transcript",
                    "text": result.text,
                    "speaker": result.speaker,
                    "confidence": result.confidence,
                    "timestamp": timestamp,
                }
            )

        async def on_error(error: str) -> None:
            nonlocal stt_needs_reconnect
            logger.error("Deepgram meeting error: %s", error)
            stt_needs_reconnect = True
            await safe_send_json(
                {"type": "error", "message": f"Transcription error: {error}"}
            )

        # -- connect to Deepgram --------------------------------------------------

        if not settings.deepgram_api_key:
            await safe_send_json(
                {"type": "error", "message": "Deepgram API key not configured"}
            )
            return

        deepgram_handler = build_stt_handler(current_sample_rate)

        if not await deepgram_handler.connect(
            on_transcript=on_transcript, on_error=on_error
        ):
            await safe_send_json(
                {"type": "error", "message": "Failed to connect to Deepgram"}
            )
            return

        await safe_send_json(
            {
                "type": "connected",
                "message": "Connected - Start speaking",
                "meeting_id": meeting_id,
            }
        )

        async def deepgram_keepalive() -> None:
            while meeting_active:
                await asyncio.sleep(3)
                if not deepgram_handler or not deepgram_handler.is_connected:
                    continue
                # Keepalive only during inactivity windows.
                if deepgram_handler.seconds_since_last_activity() >= 2.0:
                    await deepgram_handler.keepalive()

        keepalive_task = asyncio.create_task(deepgram_keepalive())

        async def reconnect_stt_if_needed() -> None:
            nonlocal deepgram_handler, stt_needs_reconnect, reconnect_attempting
            if reconnect_attempting or not stt_needs_reconnect or not meeting_active:
                return

            reconnect_attempting = True
            try:
                logger.warning("Attempting Deepgram STT reconnect for meeting %s", meeting_id)
                if deepgram_handler:
                    await deepgram_handler.disconnect()

                deepgram_handler = build_stt_handler(current_sample_rate)
                connected = await deepgram_handler.connect(
                    on_transcript=on_transcript,
                    on_error=on_error,
                )
                if connected:
                    stt_needs_reconnect = False
                    await safe_send_json(
                        {"type": "status", "message": "Transcription stream reconnected."}
                    )
                else:
                    await safe_send_json(
                        {"type": "error", "message": "Failed to reconnect transcription stream."}
                    )
            except Exception as exc:
                logger.error("Deepgram reconnect failed: %s", exc, exc_info=True)
            finally:
                reconnect_attempting = False

        summary_task = asyncio.create_task(
            summarize_periodically(
                transcript_path,
                websocket,
                initial_delay=compute_initial_periodic_delay_seconds(transcript_path),
            )
        )

        # -- main message loop ----------------------------------------------------

        while meeting_active:
            try:
                message = await asyncio.wait_for(
                    websocket.receive(), timeout=settings.websocket_timeout
                )
            except asyncio.TimeoutError:
                logger.warning("WebSocket timeout: %s", meeting_id)
                break

            msg_type = message.get("type")
            if msg_type == "websocket.disconnect":
                logger.info("Client disconnected event: %s", meeting_id)
                break

            text_data = message.get("text")
            bytes_data = message.get("bytes")

            if text_data == "STOP":
                logger.info("Meeting stopped: %s", meeting_id)
                meeting_active = False

                if summary_task:
                    summary_task.cancel()
                    try:
                        await summary_task
                    except asyncio.CancelledError:
                        pass
                    summary_task = None

                await deepgram_handler.finish()
                await safe_send_json(
                    {"type": "status", "message": "Generating final summary..."}
                )

                full_transcript = ""
                try:
                    with open(transcript_path, "r", encoding="utf-8") as f:
                        full_transcript = f.read()

                    if len(full_transcript.strip()) > 100:
                        summary_prompt = (
                            "You are an expert meeting summarizer. Create a comprehensive final summary.\n"
                            "Use only facts that are explicitly present in the transcript.\n"
                            "Do not infer or invent names, locations, dates, numbers, owners, or deadlines.\n"
                            "If a detail is missing, write 'Not specified in transcript'.\n\n"
                            "Return Markdown with exactly these sections and bullet lists only (no tables):\n"
                            "## Overview\n"
                            "## Key Takeaways\n"
                            "## Decisions\n"
                            "## Action Items\n"
                            "- include owner and deadline when available\n"
                            "## Deadlines\n"
                            "## Risks / Blockers\n"
                            "## Participants\n\n"
                            f"Transcript:\n{full_transcript}\n\n"
                            "Be explicit and concrete."
                        )
                        final_summary = await query_llm(
                            summary_prompt,
                            max_retries=2,
                            temperature=0.2,
                        )

                        with open(summary_path, "w", encoding="utf-8") as f:
                            f.write(final_summary)

                        await save_meeting_summary(user_id, meeting_id, final_summary)
                        await safe_send_json(
                            {"type": "final_summary", "summary": final_summary}
                        )
                    else:
                        await safe_send_json(
                            {
                                "type": "error",
                                "message": "Transcript too short for summary",
                            }
                        )
                except Exception as exc:
                    logger.error("Summary generation error: %s", exc, exc_info=True)
                    fallback_summary = _fallback_summary_from_transcript(full_transcript)
                    with open(summary_path, "w", encoding="utf-8") as f:
                        f.write(fallback_summary)
                    await save_meeting_summary(user_id, meeting_id, fallback_summary)
                    await safe_send_json(
                        {"type": "final_summary", "summary": fallback_summary}
                    )
                    await safe_send_json(
                        {
                            "type": "error",
                            "message": "LLM summary failed. Generated fallback summary from transcript.",
                        }
                    )
                continue

            # -- config / handshake -----------------------------------------------
            if text_data and text_data.startswith('{') and '"config"' in text_data:
                try:
                    config = json.loads(text_data)
                    if config.get("type") == "config":
                        new_rate = config.get("sample_rate")
                        if new_rate and new_rate != deepgram_handler.sample_rate:
                            logger.info("Reconfiguring Deepgram for meeting %s with sample rate: %d", 
                                        meeting_id, new_rate)
                            current_sample_rate = new_rate
                            await deepgram_handler.disconnect()
                            deepgram_handler = build_stt_handler(current_sample_rate)
                            await deepgram_handler.connect(on_transcript=on_transcript, on_error=on_error)
                        continue
                except Exception as exc:
                    logger.warning("Failed to process config message: %s", exc)
                    continue

            elif text_data and text_data.startswith("ACTION: EMAIL"):
                email = text_data.replace("ACTION: EMAIL", "").strip()
                try:
                    with open(summary_path, "r", encoding="utf-8") as f:
                        summary = f.read()
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: send_meeting_summary_email(
                            email, f"Meeting Summary - {meeting_id}", summary
                        ),
                    )
                    await safe_send_json(
                        {"type": "status", "message": f"Summary emailed to {email}"}
                    )
                except Exception as exc:
                    logger.error("Email error: %s", exc)
                    await safe_send_json(
                        {"type": "error", "message": "Failed to send email"}
                    )
                continue

            elif text_data == "ACTION: NOTION":
                try:
                    with open(summary_path, "r", encoding="utf-8") as f:
                        summary = f.read()
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: push_meeting_summary_to_notion(
                            summary, f"Meeting {meeting_id}"
                        ),
                    )
                    await safe_send_json(
                        {"type": "status", "message": "Exported to Notion"}
                    )
                except Exception as exc:
                    logger.error("Notion export error: %s", exc)
                    await safe_send_json(
                        {"type": "error", "message": "Failed to export to Notion"}
                    )
                continue

            # -- audio data -------------------------------------------------------
            if meeting_active:
                try:
                    await reconnect_stt_if_needed()
                    pcm_data = None
                    if bytes_data:
                        # Preferred fast path: raw PCM16 bytes over websocket binary frames.
                        pcm_data = bytes_data
                    elif text_data:
                        # Backward-compatible fallback: base64-encoded text frames.
                        pcm_data = process_browser_audio(text_data)
                    if pcm_data:
                        # Keep chunk logging lightweight on hot path.
                        count = getattr(websocket, "_chunk_count", 0) + 1
                        websocket._chunk_count = count
                        if count == 1:
                            logger.info("Received first audio chunk (%d bytes PCM) @ %dHz", 
                                        len(pcm_data), deepgram_handler.sample_rate)
                        elif count % 200 == 0:
                            logger.info(
                                "Received chunk %d (%d bytes PCM) @ %dHz",
                                count,
                                len(pcm_data),
                                deepgram_handler.sample_rate,
                            )
                        sent = await deepgram_handler.send_audio(pcm_data)
                        if not sent:
                            stt_needs_reconnect = True
                    else:
                        # Likely the config message or STOP message was caught here if not handled above
                        pass
                except Exception as exc:
                    logger.error("Audio processing error: %s", exc, exc_info=True)

    except WebSocketDisconnect:
        logger.info("Client disconnected: %s", meeting_id)
    except Exception as exc:
        logger.error("Meeting WebSocket error: %s", exc, exc_info=True)
    finally:
        if deepgram_handler:
            await deepgram_handler.disconnect()
        if keepalive_task:
            keepalive_task.cancel()
            try:
                await keepalive_task
            except asyncio.CancelledError:
                pass
        if summary_task:
            summary_task.cancel()
            try:
                await summary_task
            except asyncio.CancelledError:
                pass
        logger.info("Meeting ended: %s", meeting_id)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@router.get("/history", response_model=list[MeetingListItem])
async def meeting_history(
    current_user: str = Depends(get_current_user),
) -> list[MeetingListItem]:
    """List recent meetings."""
    meetings = await list_meetings(current_user)
    return [MeetingListItem(**m) for m in meetings]


@router.get("/{meeting_id}/transcript", response_model=MeetingTranscriptResponse)
async def meeting_transcript_endpoint(
    meeting_id: str,
    current_user: str = Depends(get_current_user),
) -> MeetingTranscriptResponse:
    """Retrieve the full transcript for a meeting."""
    validate_meeting_id(meeting_id)
    transcript = await get_meeting_transcript(current_user, meeting_id)
    if not transcript:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found")
    return MeetingTranscriptResponse(meeting_id=meeting_id, transcript=transcript)


@router.get("/{meeting_id}/summary", response_model=MeetingSummaryResponse)
async def meeting_summary_endpoint(
    meeting_id: str,
    current_user: str = Depends(get_current_user),
) -> MeetingSummaryResponse:
    """Retrieve the summary for a meeting."""
    validate_meeting_id(meeting_id)
    summary = await get_meeting_summary(current_user, meeting_id)
    return MeetingSummaryResponse(meeting_id=meeting_id, summary=summary)


@router.post("/{meeting_id}/chat", response_model=MeetingChatResponse)
async def meeting_chat(
    meeting_id: str,
    request: MeetingChatRequest,
    current_user: str = Depends(get_current_user),
) -> MeetingChatResponse:
    """
    Chat about a completed meeting using its transcript as context.

    Accepts text or optional voice input (base64 PCM audio).
    """
    validate_meeting_id(meeting_id)
    query = request.query

    # Handle voice input: transcribe audio to text
    if request.voice_audio and not query.strip():
        from app.services.deepgram import get_file_transcriber

        transcriber = get_file_transcriber()
        pcm_bytes = process_browser_audio(request.voice_audio)
        if pcm_bytes:
            query = await transcriber.transcribe(pcm_bytes)
        if not query:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not transcribe voice input",
            )

    if not query or not query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query cannot be empty",
        )

    transcript = await get_meeting_transcript(current_user, meeting_id)
    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting transcript not found",
        )

    query_lower = query.lower()
    summary = await get_meeting_summary(current_user, meeting_id)

    # Action command: push summary to Notion.
    if "notion" in query_lower and any(
        token in query_lower for token in ("push", "send", "save", "export", "upload")
    ):
        if not summary:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No meeting summary available yet. Generate a summary first.",
            )
        loop = asyncio.get_running_loop()
        ok = await loop.run_in_executor(
            None,
            lambda: push_meeting_summary_to_notion(summary, f"Meeting {meeting_id}"),
        )
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to export summary to Notion",
            )
        return MeetingChatResponse(response="Done. I pushed this meeting summary to Notion.")

    # Action command: email summary to one or more recipients.
    if any(token in query_lower for token in ("email", "mail", "gmail", "send to")):
        recipients = re.findall(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            query,
        )
        if recipients:
            if not summary:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No meeting summary available yet. Generate a summary first.",
                )
            loop = asyncio.get_running_loop()
            sent: list[str] = []
            failed: list[str] = []
            for recipient in recipients:
                ok = await loop.run_in_executor(
                    None,
                    lambda r=recipient: send_meeting_summary_email(
                        r, f"Meeting Summary - {meeting_id}", summary
                    ),
                )
                if ok:
                    sent.append(recipient)
                else:
                    failed.append(recipient)

            if not sent:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to send summary email to provided recipients",
                )

            response_parts = [f"Sent summary email to: {', '.join(sent)}."]
            if failed:
                response_parts.append(f"Failed: {', '.join(failed)}.")
            return MeetingChatResponse(response=" ".join(response_parts))

    prompt = (
        "You are an AI meeting assistant. Answer the user's question based on "
        "the meeting transcript below.\n\n"
        f"Transcript:\n{transcript}\n\n"
        f"User question: {query}\n\n"
        "Provide a clear, helpful answer."
    )

    response_text = await query_llm(prompt)
    return MeetingChatResponse(response=response_text)
