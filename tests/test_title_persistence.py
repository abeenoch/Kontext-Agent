"""
Unit tests for save_meeting_title() and list_meetings() title field.

Uses an in-memory SQLite database for full isolation.
"""
import os
import sys
import types
import pytest
import pytest_asyncio

# Stub chromadb and prune_old_meeting_embeddings before importing chat_memory
if "chromadb" not in sys.modules:
    chromadb_stub = types.ModuleType("chromadb")
    sys.modules["chromadb"] = chromadb_stub

# Stub vector_store to avoid chromadb dependency in chat_memory
if "app.services.vector_store" not in sys.modules:
    vs_stub = types.ModuleType("app.services.vector_store")

    async def _stub_prune(*args, **kwargs):
        pass

    vs_stub.prune_old_meeting_embeddings = lambda *a, **kw: None
    sys.modules["app.services.vector_store"] = vs_stub

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import app.services.chat_memory as chat_memory
from app.services.chat_memory import (
    Base,
    _derive_title,
    save_meeting_summary,
    save_meeting_title,
    list_meetings,
    save_meeting_chunk,
)


@pytest_asyncio.fixture
async def mem_db(monkeypatch):
    """
    Spin up a fresh in-memory SQLite engine, patch chat_memory to use it,
    run init_db(), and tear down after the test.
    """
    mem_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    mem_session = sessionmaker(mem_engine, class_=AsyncSession, expire_on_commit=False)

    # Patch the module-level engine and SessionLocal
    monkeypatch.setattr(chat_memory, "engine", mem_engine)
    monkeypatch.setattr(chat_memory, "SessionLocal", mem_session)

    # Create schema
    async with mem_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add meeting_title column (SQLite doesn't support IF NOT EXISTS in older versions)
        try:
            from sqlalchemy.sql import text
            await conn.execute(
                text("ALTER TABLE meeting_summaries ADD COLUMN meeting_title VARCHAR(80)")
            )
        except Exception:
            pass  # column may already exist from metadata

    yield mem_engine

    await mem_engine.dispose()


@pytest.mark.asyncio
async def test_list_meetings_returns_saved_title(mem_db):
    """After saving summary + title, list_meetings() returns the correct title."""
    user_id = "user-title-test"
    meeting_id = "meeting-abc123"

    # Need at least one transcript chunk so the meeting appears in list_meetings
    await save_meeting_chunk(user_id, meeting_id, "Hello world transcript chunk")
    await save_meeting_summary(user_id, meeting_id, "## Sprint Review\nWe shipped the feature.")
    await save_meeting_title(user_id, meeting_id, "Sprint Review")

    meetings = await list_meetings(user_id)
    assert len(meetings) == 1
    assert meetings[0]["title"] == "Sprint Review"
    assert meetings[0]["meeting_id"] == meeting_id


@pytest.mark.asyncio
async def test_list_meetings_fallback_title_when_no_summary(mem_db):
    """A meeting with no summary row returns a non-empty fallback title."""
    user_id = "user-fallback-test"
    meeting_id = "meeting-nosummary"

    # Only a transcript chunk — no summary row
    await save_meeting_chunk(user_id, meeting_id, "Just a transcript, no summary yet")

    meetings = await list_meetings(user_id)
    assert len(meetings) == 1
    title = meetings[0]["title"]
    assert title  # non-empty
    assert isinstance(title, str)
    # Should fall back to "Meeting on ..." or "Untitled Meeting"
    assert title.startswith("Meeting on ") or title == "Untitled Meeting"
