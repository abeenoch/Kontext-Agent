"""Database models and data access layer.

Uses SQLAlchemy async with aiosqlite for:
- User accounts (signup/login)
- Chat message history
- Meeting transcripts and summaries
"""

import time
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func, text

DATABASE_URL = "sqlite+aiosqlite:///./memory.db"
engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class User(Base):
    """Registered user account."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(Base):
    """Persisted chat message."""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    role = Column(String)  # "user" | "assistant"
    content = Column(Text)
    timestamp = Column(Float)


class MeetingTranscript(Base):
    """Individual transcript chunk from a meeting."""

    __tablename__ = "meeting_transcripts"

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(String, index=True)
    speaker = Column(String, nullable=True)
    text = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())


class MeetingSummary(Base):
    """Final or periodic summary of a meeting."""

    __tablename__ = "meeting_summaries"

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(String, index=True, unique=True)
    summary = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Database init
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Create all tables if they do not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ---------------------------------------------------------------------------
# User operations
# ---------------------------------------------------------------------------


async def create_user(email: str, password_hash: str, display_name: str = "") -> User:
    """
    Insert a new user record.

    Args:
        email: Unique email address.
        password_hash: Bcrypt-hashed password.
        display_name: Optional display name.

    Returns:
        The created User instance.
    """
    async with SessionLocal() as session:
        user = User(
            email=email,
            password_hash=password_hash,
            display_name=display_name or email.split("@")[0],
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def get_user_by_email(email: str) -> User | None:
    """Look up a user by email. Returns None if not found."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.email == email)
        )
        return result.scalars().first()


# ---------------------------------------------------------------------------
# Chat history operations
# ---------------------------------------------------------------------------


async def add_message(user_id: str, role: str, content: str) -> None:
    """Persist a chat message."""
    async with SessionLocal() as session:
        session.add(
            ChatMessage(
                user_id=user_id,
                role=role,
                content=content,
                timestamp=time.time(),
            )
        )
        await session.commit()


async def get_recent_history(user_id: str, limit: int = 5) -> list[dict[str, str]]:
    """Return the last *limit* messages for a user, oldest first."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id)
            .order_by(ChatMessage.timestamp.desc())
            .limit(limit)
        )
        messages = result.scalars().all()
        return [{"role": m.role, "content": m.content} for m in reversed(messages)]


async def clear_history(user_id: str) -> None:
    """Delete all chat messages for a user."""
    async with SessionLocal() as session:
        await session.execute(
            text("DELETE FROM chat_messages WHERE user_id = :uid"),
            {"uid": user_id},
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Meeting operations
# ---------------------------------------------------------------------------


async def save_meeting_chunk(meeting_id: str, text_content: str) -> None:
    """Append a transcript chunk to a meeting."""
    async with SessionLocal() as session:
        session.add(MeetingTranscript(meeting_id=meeting_id, text=text_content))
        await session.commit()


async def save_meeting_summary(meeting_id: str, summary: str) -> None:
    """Create or update the summary for a meeting."""
    async with SessionLocal() as session:
        existing = await session.execute(
            text("SELECT id FROM meeting_summaries WHERE meeting_id = :mid"),
            {"mid": meeting_id},
        )
        row = existing.fetchone()
        if row:
            await session.execute(
                text(
                    "UPDATE meeting_summaries SET summary = :summary "
                    "WHERE meeting_id = :mid"
                ),
                {"summary": summary, "mid": meeting_id},
            )
        else:
            session.add(MeetingSummary(meeting_id=meeting_id, summary=summary))
        await session.commit()


async def get_meeting_summary(meeting_id: str) -> str | None:
    """Retrieve the summary for a meeting."""
    async with SessionLocal() as session:
        result = await session.execute(
            text("SELECT summary FROM meeting_summaries WHERE meeting_id = :mid"),
            {"mid": meeting_id},
        )
        row = result.fetchone()
        return row[0] if row else None


async def get_meeting_transcript(meeting_id: str) -> str:
    """Retrieve the full concatenated transcript for a meeting."""
    async with SessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT text FROM meeting_transcripts "
                "WHERE meeting_id = :mid ORDER BY id ASC"
            ),
            {"mid": meeting_id},
        )
        rows = result.fetchall()
        return " ".join(r[0] for r in rows)


async def list_meetings(limit: int = 50) -> list[dict]:
    """Return a list of recent meetings with their metadata."""
    async with SessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT DISTINCT meeting_id, MIN(timestamp) as started_at "
                "FROM meeting_transcripts "
                "GROUP BY meeting_id "
                "ORDER BY started_at DESC "
                "LIMIT :limit"
            ),
            {"limit": limit},
        )
        rows = result.fetchall()
        meetings = []
        for row in rows:
            has_summary = await get_meeting_summary(row[0])
            meetings.append(
                {
                    "meeting_id": row[0],
                    "started_at": str(row[1]) if row[1] else None,
                    "has_summary": has_summary is not None,
                }
            )
        return meetings
