import pytest
from datetime import datetime

from app.services.chat_memory import _derive_title


def test_heading_extracted():
    """Summary with ## heading → title is the heading text."""
    summary = "## My Heading\nSome body text here."
    assert _derive_title(summary) == "My Heading"


def test_heading_truncated_to_80():
    """Summary with a very long ## heading → title is truncated to 80 chars."""
    long_heading = "A Very Long Heading That Exceeds Eighty Characters In Total Length Here"
    summary = f"## {long_heading}\nBody text."
    result = _derive_title(summary)
    assert result == long_heading[:80]
    assert len(result) <= 80


def test_no_heading_uses_first_sentence():
    """Summary with no heading → title is first sentence truncated to 80 chars."""
    summary = "This is the first sentence. This is the second sentence."
    result = _derive_title(summary)
    assert result == "This is the first sentence"
    assert len(result) <= 80


def test_empty_summary_with_datetime_started_at():
    """Empty string summary + started_at as datetime → title starts with 'Meeting on '."""
    started_at = datetime(2026, 4, 15, 14, 30, 0)
    result = _derive_title("", started_at)
    assert result.startswith("Meeting on ")


def test_none_summary_with_iso_string_started_at():
    """None summary + started_at as ISO string → title starts with 'Meeting on '."""
    result = _derive_title(None, "2026-04-15T14:30:00")
    assert result.startswith("Meeting on ")


def test_none_summary_none_started_at():
    """None summary + None started_at → title is 'Untitled Meeting'."""
    result = _derive_title(None, None)
    assert result == "Untitled Meeting"
