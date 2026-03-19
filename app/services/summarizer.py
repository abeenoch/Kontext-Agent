import asyncio
import os
from datetime import datetime

from fastapi import WebSocket

from app.services.llm_agent import query_llm
from app.services.chat_memory import save_periodic_summary
from app.logger import get_logger

logger = get_logger(__name__)

SUMMARY_INTERVAL_SECONDS = 300  # generate periodic summary every 5 minutes


async def summarize_periodically(
    transcript_path: str,
    websocket: WebSocket,
    interval: int = SUMMARY_INTERVAL_SECONDS,
    initial_delay: int | None = None,
    user_id: str | None = None,
    meeting_id: str | None = None,
) -> None:
    """
    Background task that reads the growing transcript file and
    sends periodic summaries over the WebSocket.

    Args:
        transcript_path: Path to the transcript text file.
        websocket: WebSocket connection to send summaries to.
        interval: Seconds between summary generations.
    """
    if initial_delay is None:
        initial_delay = interval

    await asyncio.sleep(max(1, initial_delay))

    while True:

        if not os.path.exists(transcript_path):
            await asyncio.sleep(15)
            continue

        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                transcript = f.read()

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
                f"Transcript:\n{transcript}\n\n"
                "Periodic update:"
            )

            summary = await query_llm(prompt, max_retries=1, temperature=0.2)

            if summary:
                if user_id and meeting_id:
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


def compute_initial_periodic_delay_seconds(
    transcript_path: str,
    interval: int = SUMMARY_INTERVAL_SECONDS,
) -> int:
    """Align first periodic summary to original meeting start time when possible."""
    try:
        if not os.path.exists(transcript_path):
            return interval
        with open(transcript_path, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
        prefix = "Meeting Transcript - "
        if not first_line.startswith(prefix):
            return interval
        started = datetime.strptime(first_line[len(prefix):], "%Y-%m-%d %H:%M:%S")
        elapsed = (datetime.now() - started).total_seconds()
        remaining = interval - int(elapsed % interval)
        return max(1, remaining)
    except Exception:
        return interval
