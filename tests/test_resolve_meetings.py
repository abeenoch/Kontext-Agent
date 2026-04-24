

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.services.meeting_search import resolve_meetings


REFERENCE_DT = datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_meeting(meeting_id: str, started_at: str, title: str = "Test Meeting") -> dict:
    return {"meeting_id": meeting_id, "title": title, "started_at": started_at}



@pytest.mark.asyncio
async def test_temporal_match_returns_matching_ids():
    meetings = [
        _make_meeting("meeting-id-1", "2026-04-14T14:30:00+00:00", "Monday standup"),
        _make_meeting("meeting-id-2", "2026-04-13T10:00:00+00:00", "Sunday review"),
    ]
    llm_response = json.dumps({
        "has_temporal": True,
        "start_iso": "2026-04-14T00:00:00",
        "end_iso": "2026-04-14T23:59:59",
        "description": "Monday Apr 14",
    })

    with patch("app.services.meeting_search.query_llm", new=AsyncMock(return_value=llm_response)):
        ids, description = await resolve_meetings("user-1", "what happened Monday?", REFERENCE_DT, meetings)

    assert ids == ["meeting-id-1"]
    assert description == "Monday Apr 14"



@pytest.mark.asyncio
async def test_no_temporal_reference_returns_none():
    meetings = [
        _make_meeting("meeting-id-1", "2026-04-14T14:30:00+00:00"),
    ]
    llm_response = json.dumps({
        "has_temporal": False,
        "start_iso": None,
        "end_iso": None,
        "description": None,
    })

    with patch("app.services.meeting_search.query_llm", new=AsyncMock(return_value=llm_response)):
        ids, description = await resolve_meetings("user-1", "what are the action items?", REFERENCE_DT, meetings)

    assert ids is None
    assert description is None


@pytest.mark.asyncio
async def test_temporal_match_no_meetings_in_range():
    meetings = [
        _make_meeting("meeting-id-1", "2026-04-10T14:30:00+00:00", "Old meeting"),
    ]
    llm_response = json.dumps({
        "has_temporal": True,
        "start_iso": "2026-04-14T00:00:00",
        "end_iso": "2026-04-14T23:59:59",
        "description": "Monday Apr 14",
    })

    with patch("app.services.meeting_search.query_llm", new=AsyncMock(return_value=llm_response)):
        ids, description = await resolve_meetings("user-1", "what happened Monday?", REFERENCE_DT, meetings)

    assert ids == []
    assert description == "Monday Apr 14"



@pytest.mark.asyncio
async def test_llm_failure_returns_none():
    meetings = [
        _make_meeting("meeting-id-1", "2026-04-14T14:30:00+00:00"),
    ]

    with patch("app.services.meeting_search.query_llm", new=AsyncMock(side_effect=RuntimeError("LLM down"))):
        ids, description = await resolve_meetings("user-1", "what happened Monday?", REFERENCE_DT, meetings)

    assert ids is None
    assert description is None



@pytest.mark.asyncio
async def test_meeting_list_truncated_to_50():
    # Create 60 meetings with distinct dates
    meetings = [
        _make_meeting(f"meeting-{i}", f"2026-04-{i % 28 + 1:02d}T10:00:00+00:00")
        for i in range(60)
    ]
    llm_response = json.dumps({
        "has_temporal": False,
        "start_iso": None,
        "end_iso": None,
        "description": None,
    })

    captured_prompts = []

    async def mock_llm(prompt, temperature=None):
        captured_prompts.append(prompt)
        return llm_response

    with patch("app.services.meeting_search.query_llm", new=mock_llm):
        await resolve_meetings("user-1", "anything", REFERENCE_DT, meetings)

    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    # The prompt should list exactly 50 meetings (numbered 1. through 50.)
    assert "50." in prompt
    assert "51." not in prompt
