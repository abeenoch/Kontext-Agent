"""Tests for POST /meeting/search endpoint."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.meeting_search import CrossMeetingSearchResult, SourceMeeting

MOCK_RESULT = CrossMeetingSearchResult(
    answer="We discussed the Q1 roadmap yesterday.",
    sources=[
        SourceMeeting(
            meeting_id="abc123",
            title="Q1 Planning",
            started_at="2026-04-13T10:00:00",
        )
    ],
    temporal_range="yesterday",
)


def test_search_unauthenticated(client):
    """No auth header → 401 or 403."""
    resp = client.post("/meeting/search", json={"query": "what happened yesterday?"})
    assert resp.status_code in (401, 403)


def test_search_empty_query(client, auth_headers):
    """Empty query string → 422."""
    with patch(
        "app.routes.meeting.cross_meeting_search",
        new_callable=AsyncMock,
    ) as mock_search:
        resp = client.post("/meeting/search", json={"query": ""}, headers=auth_headers)
    assert resp.status_code == 422
    mock_search.assert_not_called()


def test_search_valid_request(client, auth_headers):
    """Valid query → 200 with CrossMeetingSearchResult shape."""
    with patch(
        "app.routes.meeting.cross_meeting_search",
        new_callable=AsyncMock,
        return_value=MOCK_RESULT,
    ):
        resp = client.post(
            "/meeting/search",
            json={"query": "what happened yesterday?"},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "sources" in data
    assert "temporal_range" in data
    assert data["answer"] == MOCK_RESULT.answer


def test_search_date_hint_forwarded(client, auth_headers):
    """date_hint is forwarded correctly to cross_meeting_search."""
    date_hint = "2026-04-14T00:00:00"
    with patch(
        "app.routes.meeting.cross_meeting_search",
        new_callable=AsyncMock,
        return_value=MOCK_RESULT,
    ) as mock_search:
        resp = client.post(
            "/meeting/search",
            json={"query": "test", "date_hint": date_hint},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    mock_search.assert_called_once()
    call_kwargs = mock_search.call_args
    # Positional: (user_id, query, date_hint)
    assert call_kwargs.args[1] == "test"
    assert call_kwargs.args[2] == date_hint
