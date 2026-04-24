import json
import re
from datetime import datetime, timezone

from pydantic import BaseModel

from app.logger import get_logger
from app.services.chat_memory import list_meetings
from app.services.llm_agent import query_llm
from app.services.vector_store import query_meetings

logger = get_logger(__name__)


class SourceMeeting(BaseModel):
    meeting_id: str
    title: str
    started_at: str | None


class CrossMeetingSearchResult(BaseModel):
    answer: str
    sources: list[SourceMeeting]
    temporal_range: str | None


def _parse_started_at(started_at: str) -> datetime | None:
    """Parse a started_at string into a timezone-aware datetime. Returns None on failure."""
    try:
        dt = datetime.fromisoformat(started_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


async def resolve_meetings(
    user_id: str,
    query: str,
    reference_dt: datetime,
    meetings: list[dict],
) -> tuple[list[str] | None, str | None]:
    """
    Use the LLM to extract a time window from the query and return matching meeting IDs.

    Returns:
        (meeting_ids, resolved_range_description)
        - meeting_ids: list of IDs, empty list if temporal match found nothing,
          or None if no temporal reference detected (caller should do unfiltered search)
        - resolved_range_description: human-readable string like "Tuesday Apr 15" or None
    """
    try:
        # Truncate to 50 most recent (already ordered DESC from list_meetings)
        truncated = meetings[:50]

        # Format meeting list for the prompt
        meeting_lines = []
        for i, m in enumerate(truncated, start=1):
            meeting_lines.append(
                f"{i}. meeting_id={m.get('meeting_id', '')} | "
                f"title={m.get('title', '')} | "
                f"started_at={m.get('started_at', 'unknown')}"
            )
        meeting_list_str = "\n".join(meeting_lines)

        today_str = reference_dt.astimezone(timezone.utc).isoformat()

        prompt = f"""Today's UTC datetime: {today_str}

The user has the following meetings (most recent first):
{meeting_list_str}

User query: {query}

Does this query contain a temporal reference (e.g. "yesterday", "last Tuesday", "this week", "last month")?

Return ONLY valid JSON with no explanation, no markdown, no code fences:
{{"has_temporal": bool, "start_iso": str|null, "end_iso": str|null, "description": str|null}}

- "has_temporal": true if the query references a specific time period, false otherwise
- "start_iso": ISO datetime string for the start of the resolved window (null if no temporal ref)
- "end_iso": ISO datetime string for the end of the resolved window (null if no temporal ref)
- "description": human-readable description of the time window (null if no temporal ref)"""

        raw = await query_llm(prompt, temperature=0)

        # Strip markdown code fences if present
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

        parsed = json.loads(cleaned)

        if not parsed.get("has_temporal"):
            return (None, None)

        start_iso = parsed.get("start_iso")
        end_iso = parsed.get("end_iso")
        description = parsed.get("description")

        # Parse window boundaries
        start_dt = _parse_started_at(start_iso) if start_iso else None
        end_dt = _parse_started_at(end_iso) if end_iso else None

        # Filter meetings whose started_at falls within [start_iso, end_iso]
        matching_ids: list[str] = []
        for m in meetings:
            raw_started = m.get("started_at")
            if raw_started is None:
                continue
            meeting_dt = _parse_started_at(str(raw_started))
            if meeting_dt is None:
                continue
            if start_dt and meeting_dt < start_dt:
                continue
            if end_dt and meeting_dt > end_dt:
                continue
            matching_ids.append(m["meeting_id"])

        return (matching_ids, description)

    except Exception as exc:
        logger.warning("resolve_meetings failed: %s", exc)
        return (None, None)


async def cross_meeting_search(
    user_id: str,
    query: str,
    date_hint: str | None = None,
) -> CrossMeetingSearchResult:
    """
    Search across all meetings for a user, optionally filtered by a temporal hint.
    """
    # 1. Determine reference datetime
    reference_dt = (
        _parse_started_at(date_hint) if date_hint else None
    ) or datetime.now(timezone.utc)

    # 2. Fetch meetings; return early if none
    meetings = await list_meetings(user_id)
    if not meetings:
        return CrossMeetingSearchResult(
            answer="You have no meeting history yet. Start a meeting to build your history.",
            sources=[],
            temporal_range=None,
        )

    # 3. Resolve temporal filter
    meeting_ids, temporal_range = await resolve_meetings(user_id, query, reference_dt, meetings)

    # 4. Fetch chunks based on resolution result
    if meeting_ids == []:
        return CrossMeetingSearchResult(
            answer=f"No meetings found for the period: {temporal_range}. Try a different time range.",
            sources=[],
            temporal_range=temporal_range,
        )
    elif meeting_ids is None:
        chunks = await query_meetings(user_id, query, n_results=10)
    else:
        # Non-empty list: query per meeting and deduplicate
        seen: set[str] = set()
        chunks: list[str] = []
        for mid in meeting_ids:
            for chunk in await query_meetings(user_id, query, meeting_id=mid, n_results=10):
                if chunk not in seen:
                    seen.add(chunk)
                    chunks.append(chunk)
        chunks = chunks[:10]

    # 5. No chunks found
    if not chunks:
        return CrossMeetingSearchResult(
            answer="I couldn't find relevant content in your meeting history for that query.",
            sources=[],
            temporal_range=temporal_range,
        )

    # 6. Build meeting lookup
    meeting_lookup = {m["meeting_id"]: m for m in meetings}

    # 7. Determine searched meetings
    if meeting_ids is None:
        searched_meetings = meetings[:5]
    else:
        searched_meetings = [meeting_lookup[mid] for mid in meeting_ids if mid in meeting_lookup]

    # 8. Build header string
    header_lines = []
    for m in searched_meetings:
        header_lines.append(f"- {m.get('title', '')} (started: {m.get('started_at', 'unknown')})")
    header = "\n".join(header_lines)

    # 9. Build numbered chunks string
    numbered_chunks = "\n\n".join(f"{i}. {chunk}" for i, chunk in enumerate(chunks, start=1))

    # 10. Build prompt
    prompt = (
        "You are an AI meeting assistant. Answer the user's question using the meeting content below.\n"
        "Always cite which meeting the information came from when possible.\n\n"
        f"Meetings searched:\n{header}\n\n"
        f"Relevant content:\n{numbered_chunks}\n\n"
        f"User question: {query}\n\n"
        "Provide a clear, helpful answer. If you reference specific information, mention which meeting it came from."
    )

    # 11. Query LLM with fallback
    try:
        answer = await query_llm(prompt)
    except Exception:
        answer = "Note: AI synthesis unavailable.\n\n" + "\n\n---\n\n".join(chunks)

    # 12. Build sources
    sources = [
        SourceMeeting(
            meeting_id=m["meeting_id"],
            title=m.get("title", ""),
            started_at=m.get("started_at"),
        )
        for m in searched_meetings
    ]

    # 13. Return result
    return CrossMeetingSearchResult(answer=answer, sources=sources, temporal_range=temporal_range)
