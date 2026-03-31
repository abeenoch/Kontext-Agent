import asyncio

from fastapi import WebSocket

from app.services.llm_agent import query_llm
from app.services.chat_memory import save_periodic_summary, get_recent_transcript_window
from app.utils.redaction import redact_pii
from app.config import get_settings
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

SUMMARY_INTERVAL_SECONDS = 300  # generate periodic summary every 5 minutes


async def summarize_periodically(
    websocket: WebSocket,
    *,
    user_id: str,
    meeting_id: str,
    interval: int = SUMMARY_INTERVAL_SECONDS,
    lookback_minutes: int | None = None,
) -> None:
    """
    Background task that reads recent transcript text from the DB and
    sends periodic summaries over the WebSocket.
    """
    if lookback_minutes is None:
        lookback_minutes = settings.periodic_summary_lookback_minutes

    await asyncio.sleep(max(1, interval))

    while True:
        try:
            transcript = await get_recent_transcript_window(
                user_id=user_id,
                meeting_id=meeting_id,
                minutes=lookback_minutes,
            )

            if len(transcript.strip()) < 100:
                await asyncio.sleep(15)
                continue

            prompt = (
                "You are a concise meeting summarizer. Provide a periodic update for the meeting so far.\n\n"
                "Output in Markdown with exactly these sections:\n"
                "## Key Takeaways\n"
                "- 3 to 6 bullets of what matters most so far\n"
                "## Open Questions\n"
                "- unresolved points or risks\n"
                "## Emerging Action Items\n"
                "- tentative owners and next steps if mentioned\n\n"
                "Keep it under 180 words and avoid final conclusions.\n"
                "Only include facts present in the transcript. Do not invent names, dates, or numbers.\n\n"
                f"Transcript:\n{redact_pii(transcript)}\n\n"
                "Periodic update:"
            )

            summary = await query_llm(prompt, max_retries=3, temperature=0.2)

            if summary:
                try:
                    await save_periodic_summary(user_id, meeting_id, summary)
                except Exception as db_exc:
                    logger.warning("Failed to persist periodic summary: %s", db_exc)
                try:
                    await websocket.send_json(
                        {"type": "periodic_summary", "summary": summary}
                    )
                except Exception as send_exc:
                    # WebSocket is closing/closed: terminate periodic worker cleanly.
                    logger.info(
                        "Stopping periodic summarizer; websocket closed: %s",
                        send_exc,
                    )
                    return
                logger.debug("Periodic summary sent (%d chars)", len(summary))
                await asyncio.sleep(interval)
                continue

        except asyncio.CancelledError:
            logger.info("Periodic summarization cancelled")
            raise
        except Exception as exc:
            logger.error("Periodic summary error: %s", exc)
            if "429" in str(exc):
                await asyncio.sleep(60)
                continue

        await asyncio.sleep(15)


def compute_initial_periodic_delay_seconds(interval: int = SUMMARY_INTERVAL_SECONDS) -> int:
    """Align first periodic summary start; currently returns interval for simplicity."""
    return interval
