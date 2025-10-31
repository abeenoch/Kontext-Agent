import time
from sqlalchemy.future import select
from app.db.chat_memory_db import SessionLocal, ChatMessage, Base, engine
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import text



DATABASE_URL = "sqlite+aiosqlite:///./memory.db"
engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


# Initialize DB on startup
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def add_message(user_id: str, role: str, content: str):
    """Save a message persistently."""
    async with SessionLocal() as session:
        msg = ChatMessage(
            user_id=user_id,
            role=role,
            content=content,
            timestamp=time.time()
        )
        session.add(msg)
        await session.commit()


async def get_recent_history(user_id: str, limit: int = 5):
    """Retrieve last few messages for a user."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id)
            .order_by(ChatMessage.timestamp.desc())
            .limit(limit)
        )
        messages = result.scalars().all()
        # Return oldest-first order
        return [{"role": m.role, "content": m.content} for m in reversed(messages)]


async def clear_history(user_id: str):
    async with SessionLocal() as session:
        await session.execute(
            f"DELETE FROM chat_messages WHERE user_id = :uid", {"uid": user_id}
        )
        await session.commit()



class MeetingTranscript(Base):
    __tablename__ = "meeting_transcripts"

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(String, index=True)
    speaker = Column(String, nullable=True)
    text = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())


class MeetingSummary(Base):
    __tablename__ = "meeting_summaries"

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(String, index=True, unique=True)
    summary = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


async def init_db():
    """Initialize all tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# --- Helper functions ---
async def save_meeting_chunk(meeting_id: str, text: str):
    async with SessionLocal() as session:
        session.add(MeetingTranscript(meeting_id=meeting_id, text=text))
        await session.commit()


async def save_meeting_summary(meeting_id: str, summary: str):
    async with SessionLocal() as session:
        existing = await session.execute(
            f"SELECT id FROM meeting_summaries WHERE meeting_id='{meeting_id}'"
        )
        row = existing.fetchone()
        if row:
            await session.execute(
                f"UPDATE meeting_summaries SET summary='{summary}' WHERE meeting_id='{meeting_id}'"
            )
        else:
            session.add(MeetingSummary(meeting_id=meeting_id, summary=summary))
        await session.commit()



async def get_meeting_summary(meeting_id: str):
    async with SessionLocal() as session:
        result = await session.execute(
            text("SELECT summary FROM meeting_summaries WHERE meeting_id = :meeting_id"),
            {"meeting_id": meeting_id}
        )
        row = result.fetchone()
        return row[0] if row else None


async def get_meeting_transcript(meeting_id: str):
    async with SessionLocal() as session:
        result = await session.execute(
            text("SELECT text FROM meeting_transcripts WHERE meeting_id = :meeting_id ORDER BY id ASC"),
            {"meeting_id": meeting_id}
        )
        rows = result.fetchall()
        return " ".join(r[0] for r in rows)