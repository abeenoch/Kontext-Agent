import asyncio

from fastapi import WebSocket

from app.services.llm_agent import query_llm
from app.services.chat_memory import (
    save_periodic_summary,
    get_recent_transcript_window,
    get_latest_periodic_summary,
)
from app.prompts import PERIODIC_SUMMARY_SYSTEM_PROMPT, build_periodic_summary_user
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

            previous_summary = None
            try:
                previous_summary = await get_latest_periodic_summary(user_id, meeting_id)
            except Exception as exc:
                logger.debug("Could not load previous periodic summary: %s", exc)

            user_prompt = build_periodic_summary_user(
                previous_summary, redact_pii(transcript)
            )

            summary = await query_llm(
                user_prompt,
                max_retries=3,
                temperature=0.2,
                system_prompt=PERIODIC_SUMMARY_SYSTEM_PROMPT,
            )

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
