import asyncio
import json
import re
import os
import time
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
    save_meeting_title,
    _derive_title,
    get_meeting_summary,
    get_meeting_transcript,
    get_meeting_title,
    list_meetings,
    delete_meeting_data,
    upsert_meeting_session,
    get_active_meeting,
    mark_meeting_stopped,
)
from app.services.vector_store import (
    ensure_user_collections,
    add_meeting_chunk_embedding,
    add_meeting_summary_embedding,
    add_full_transcript_embeddings,
    query_meetings,
    delete_meeting_embeddings,
)
from app.services.meeting_search import cross_meeting_search, CrossMeetingSearchResult
from app.auth import get_current_user, get_current_user_ws
from app.config import get_settings
from app.logger import get_logger
from app.validators import validate_meeting_id
from app.utils.redaction import redact_pii
import httpx

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/meeting", tags=["Meeting"])

# Track active meeting sessions per user to allow reconnect without losing meeting_id.
_active_meetings: dict[str, dict] = {}


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





class MeetingChatRequest(BaseModel):
    """Post-meeting chat request."""
    query: str
    voice_audio: str | None = None  # optional base64 PCM for voice input


class MeetingSearchRequest(BaseModel):
    """Cross-meeting search request."""
    query: str
    date_hint: str | None = None


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
    title: str = ""



@router.websocket("/ws")
async def meeting_websocket(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time meeting transcription with Deepgram."""
    user_id = await get_current_user_ws(websocket)

    requested_meeting_id = websocket.query_params.get("meeting_id")
    meeting_id: str
    if requested_meeting_id:
        try:
            meeting_id = validate_meeting_id(requested_meeting_id)
        except HTTPException:
            await websocket.close(code=1008)
            return
    else:
        # If user already has an active meeting, reuse it so reconnections keep the same session.
        existing = await get_active_meeting(user_id)
        if existing:
            meeting_id = existing
            logger.info("Reusing active meeting %s for user %s", meeting_id, user_id)
        else:
            meeting_id = os.urandom(16).hex()

    try:
        await ensure_user_collections(user_id)
    except Exception as exc:
        logger.warning("Could not ensure Chroma collections for %s: %s", user_id, exc)

    await websocket.accept()
    logger.info("Meeting started: %s", meeting_id)

    deepgram_handler: DeepgramSTTHandler | None = None
    meeting_active = True
    summary_task: asyncio.Task | None = None
    keepalive_task: asyncio.Task | None = None
    ping_task: asyncio.Task | None = None
    current_sample_rate = 16000
    stt_needs_reconnect = False
    reconnect_attempting = False
    stopped_gracefully = False

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

    # Record the active meeting for reconnects
    try:
        await upsert_meeting_session(user_id, meeting_id)
    except Exception as exc:
        logger.warning("Failed to persist meeting session: %s", exc)

    try:
        

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
            try:
                chunk_id, chunk_ts = await save_meeting_chunk(user_id, meeting_id, transcript_line)
                timestamp = datetime.fromtimestamp(chunk_ts.timestamp()).strftime("%H:%M:%S")
                asyncio.create_task(
                    add_meeting_chunk_embedding(
                        user_id=user_id,
                        meeting_id=meeting_id,
                        text=transcript_line,
                        speaker=str(result.speaker) if result.speaker is not None else None,
                        chunk_index=chunk_id,
                        created_at=chunk_ts.timestamp(),
                    )
                )
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
                {
                    "type": "status",
                    "message": "Transcription stream hiccup detected; reconnecting...",
                }
            )

        

        if not settings.deepgram_api_key:
            await safe_send_json(
                {"type": "error", "message": "Deepgram API key not configured"}
            )
            return

        deepgram_handler = build_stt_handler(current_sample_rate)

        async def try_connect(attempt: int) -> bool:
            if await deepgram_handler.connect(
                on_transcript=on_transcript, on_error=on_error
            ):
                return True
            logger.warning("Deepgram connect attempt %d failed", attempt)
            return False

        connected = await try_connect(1)
        if not connected:
            await asyncio.sleep(2)
            deepgram_handler = build_stt_handler(current_sample_rate)
            connected = await try_connect(2)

        if not connected:
            await safe_send_json(
                {
                    "type": "error",
                    "message": "Unable to connect to transcription service. Please retry.",
                }
            )
            await websocket.close()
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

        async def websocket_ping() -> None:
            # Heartbeat to keep proxies/browsers from timing out idle WS.
            while meeting_active:
                await asyncio.sleep(10)
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break

        ping_task = asyncio.create_task(websocket_ping())

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
                websocket,
                user_id=user_id,
                meeting_id=meeting_id,
                interval=compute_initial_periodic_delay_seconds(),
                lookback_minutes=settings.periodic_summary_lookback_minutes,
            )
        )

        

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
                stopped_gracefully = True

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

                try:
                    full_transcript = await get_meeting_transcript(user_id, meeting_id)

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
                            f"Transcript:\n{redact_pii(full_transcript)}\n\n"
                            "Be explicit and concrete."
                        )
                        final_summary = await query_llm(
                            summary_prompt,
                            max_retries=2,
                            temperature=0.2,
                        )

                        await save_meeting_summary(user_id, meeting_id, final_summary)
                        try:
                            _title = _derive_title(final_summary, datetime.now())
                            await save_meeting_title(user_id, meeting_id, _title)
                        except Exception as _exc:
                            logger.warning("Failed to save meeting title: %s", _exc)
                        asyncio.create_task(
                            add_meeting_summary_embedding(
                                user_id=user_id,
                                meeting_id=meeting_id,
                                summary_text=final_summary,
                            )
                        )
                        asyncio.create_task(
                            add_full_transcript_embeddings(
                                user_id=user_id,
                                meeting_id=meeting_id,
                                transcript_text=full_transcript,
                            )
                        )
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
                    fallback_summary = _fallback_summary_from_transcript(full_transcript if 'full_transcript' in locals() else "")
                    await save_meeting_summary(user_id, meeting_id, fallback_summary)
                    try:
                        _title = _derive_title(fallback_summary, datetime.now())
                        await save_meeting_title(user_id, meeting_id, _title)
                    except Exception as _exc:
                        logger.warning("Failed to save meeting title: %s", _exc)
                    asyncio.create_task(
                        add_meeting_summary_embedding(
                            user_id=user_id,
                            meeting_id=meeting_id,
                            summary_text=fallback_summary,
                        )
                    )
                    asyncio.create_task(
                        add_full_transcript_embeddings(
                            user_id=user_id,
                            meeting_id=meeting_id,
                            transcript_text=full_transcript if 'full_transcript' in locals() else "",
                        )
                    )
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

            # config / handshake
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
                    summary = await get_meeting_summary(user_id, meeting_id)
                    if not summary:
                        await safe_send_json({"type": "error", "message": "No summary available to email"})
                        continue
                    meeting_title = await get_meeting_title(user_id, meeting_id)
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: send_meeting_summary_email(
                            email, f"Meeting Summary - {meeting_title}", summary
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
                    summary = await get_meeting_summary(user_id, meeting_id)
                    if not summary:
                        await safe_send_json({"type": "error", "message": "No summary available to export"})
                        continue
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

            #audio data
            if meeting_active:
                try:
                    await reconnect_stt_if_needed()
                    # If reconnecting, drop audio until socket is back to avoid errors.
                    if stt_needs_reconnect or not deepgram_handler or not deepgram_handler.is_connected:
                        continue

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
        if ping_task:
            ping_task.cancel()
            try:
                await ping_task
            except asyncio.CancelledError:
                pass
        if summary_task:
            summary_task.cancel()
            try:
                await summary_task
            except asyncio.CancelledError:
                pass
        # If meeting was explicitly stopped, clear active mapping; otherwise keep for reconnect.
        if stopped_gracefully:
            _active_meetings.pop(user_id, None)
            try:
                await mark_meeting_stopped(user_id)
            except Exception as exc:
                logger.debug("Failed to mark meeting stopped: %s", exc)
            logger.info("Meeting ended: %s", meeting_id)
        else:
            logger.info("Meeting paused (awaiting reconnect): %s", meeting_id)




@router.post("/search", response_model=CrossMeetingSearchResult)
async def meeting_search(
    request: MeetingSearchRequest,
    current_user: str = Depends(get_current_user),
) -> CrossMeetingSearchResult:
    """Search across all meetings using natural language, with optional temporal filtering."""
    if not request.query or not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query cannot be empty",
        )
    return await cross_meeting_search(current_user, request.query, request.date_hint)


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


@router.delete("/{meeting_id}")
async def delete_meeting(
    meeting_id: str,
    current_user: str = Depends(get_current_user),
) -> dict:
    """User-driven hard delete of meeting transcript, summaries, and embeddings."""
    validate_meeting_id(meeting_id)
    await delete_meeting_data(current_user, meeting_id)
    try:
        delete_meeting_embeddings(current_user, meeting_id)
    except Exception as exc:
        logger.debug("Embedding cleanup failed for %s/%s: %s", current_user, meeting_id, exc)
    return {"status": "deleted", "meeting_id": meeting_id}


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
    special_any = meeting_id in {"recent", "any", "latest"}
    if not special_any:
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

    query_lower = query.lower()

    # If special "recent"/"any" mode: delegate to cross_meeting_search pipeline
    if special_any:
        result = await cross_meeting_search(current_user, query)
        return MeetingChatResponse(response=result.answer)

    transcript = await get_meeting_transcript(current_user, meeting_id)
    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting transcript not found",
        )

    summary = await get_meeting_summary(current_user, meeting_id)

    # Vector-powered retrieval scoped to this meeting for efficient context.
    context_chunks: list[str] = []
    try:
        context_chunks = await query_meetings(
            user_id=current_user,
            query=query,
            meeting_id=meeting_id,
            n_results=6,
        )
    except Exception as exc:
        logger.warning("Meeting RAG retrieval failed: %s", exc)

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
            meeting_title = await get_meeting_title(current_user, meeting_id)
            for recipient in recipients:
                ok = await loop.run_in_executor(
                    None,
                    lambda r=recipient: send_meeting_summary_email(
                        r, f"Meeting Summary - {meeting_title}", summary
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

    context_blocks: list[str] = []
    if summary:
        context_blocks.append(f"Final Summary:\n{summary}")
    if context_chunks:
        context_blocks.append("Transcript Excerpts:\n" + "\n\n".join(context_chunks))
    if not context_blocks:
        context_blocks.append(f"Full Transcript:\n{transcript}")

    # Add cross-meeting supporting context
    try:
        cross_meeting = await query_meetings(
            user_id=current_user,
            query=query,
            meeting_id=None,
            n_results=4,
        )
        if cross_meeting:
            context_blocks.append("Relevant snippets from other meetings:\n" + "\n\n".join(cross_meeting))
    except Exception as exc:
        logger.debug("Cross-meeting RAG retrieval failed: %s", exc)

    context_joined = "\n\n".join(context_blocks)
    safe_context = redact_pii(context_joined)
    sanitized_query = redact_pii(query)

    prompt = (
        "You are an AI meeting assistant. Answer the user's question using the meeting context below.\n\n"
        f"{safe_context}\n\n"
        f"User question: {sanitized_query}\n\n"
        "Provide a clear, helpful answer grounded in the provided context."
    )

    try:
        response_text = await query_llm(prompt)
        return MeetingChatResponse(response=response_text)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 503:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="LLM provider temporarily unavailable. Please retry shortly.",
            )
        raise
