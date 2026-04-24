

from unittest.mock import AsyncMock, patch

import pytest

from app.services.meeting_search import cross_meeting_search


def _make_meeting(meeting_id: str, started_at: str, title: str = "Test Meeting") -> dict:
    return {"meeting_id": meeting_id, "title": title, "started_at": started_at}


MEETINGS = [
    _make_meeting("mid-1", "2026-04-14T14:30:00+00:00", "Monday standup"),
    _make_meeting("mid-2", "2026-04-13T10:00:00+00:00", "Sunday review"),
]


@pytest.mark.asyncio
async def test_no_meetings_returns_early():
    with patch("app.services.meeting_search.list_meetings", new=AsyncMock(return_value=[])):
        result = await cross_meeting_search("user-1", "what happened yesterday?")

    assert "no meeting history" in result.answer.lower()
    assert result.sources == []
    assert result.temporal_range is None


@pytest.mark.asyncio
async def test_temporal_empty_window():
    with (
        patch("app.services.meeting_search.list_meetings", new=AsyncMock(return_value=MEETINGS)),
        patch(
            "app.services.meeting_search.resolve_meetings",
            new=AsyncMock(return_value=([], "Monday Apr 14")),
        ),
    ):
        result = await cross_meeting_search("user-1", "what happened Monday?")

    assert "No meetings found" in result.answer
    assert result.sources == []
    assert result.temporal_range == "Monday Apr 14"



@pytest.mark.asyncio
async def test_unfiltered_search_with_results():
    with (
        patch("app.services.meeting_search.list_meetings", new=AsyncMock(return_value=MEETINGS)),
        patch(
            "app.services.meeting_search.resolve_meetings",
            new=AsyncMock(return_value=(None, None)),
        ),
        patch(
            "app.services.meeting_search.query_meetings",
            new=AsyncMock(return_value=["chunk1", "chunk2"]),
        ),
        patch(
            "app.services.meeting_search.query_llm",
            new=AsyncMock(return_value="Here is the answer"),
        ),
    ):
        result = await cross_meeting_search("user-1", "what are the action items?")

    assert result.answer == "Here is the answer"
    assert len(result.sources) > 0


@pytest.mark.asyncio
async def test_llm_failure_fallback():
    with (
        patch("app.services.meeting_search.list_meetings", new=AsyncMock(return_value=MEETINGS)),
        patch(
            "app.services.meeting_search.resolve_meetings",
            new=AsyncMock(return_value=(None, None)),
        ),
        patch(
            "app.services.meeting_search.query_meetings",
            new=AsyncMock(return_value=["chunk1", "chunk2"]),
        ),
        patch(
            "app.services.meeting_search.query_llm",
            new=AsyncMock(side_effect=RuntimeError("LLM down")),
        ),
    ):
        result = await cross_meeting_search("user-1", "what are the action items?")

    # Should not raise; answer should contain raw chunk content
    assert result.answer
    assert "chunk1" in result.answer or "AI synthesis unavailable" in result.answer
