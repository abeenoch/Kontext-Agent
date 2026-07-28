import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, Index, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func, text

from app.config import get_settings
from app.services.vector_store import prune_old_meeting_embeddings
from app.utils.crypto_utils import encrypt_text, decrypt_text

_settings = get_settings()
DATABASE_URL = _settings.get_database_url()
engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()
ENCRYPTION_KEY = _settings.get_encryption_key()

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
    __table_args__ = (
        Index("idx_chat_messages_user_ts", "user_id", "timestamp"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    tab_id = Column(String, index=True, nullable=True)
    role = Column(String)  # "user" | "assistant"
    content = Column(Text)
    timestamp = Column(Float)


class MeetingTranscript(Base):
    """Individual transcript chunk from a meeting."""

    __tablename__ = "meeting_transcripts"
    __table_args__ = (
        Index("idx_meeting_transcripts_user_meeting", "user_id", "meeting_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False, default="legacy")
    meeting_id = Column(String, index=True)
    speaker = Column(String, nullable=True)
    text = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())


class MeetingSummary(Base):
    """Final or periodic summary of a meeting."""

    __tablename__ = "meeting_summaries"
    __table_args__ = (
        UniqueConstraint("user_id", "meeting_id", name="ux_meeting_summary_user_meeting"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False, default="legacy")
    meeting_id = Column(String, index=True)
    summary = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class MeetingPeriodicSummary(Base):
    """Periodic (in-meeting) summary snapshots."""

    __tablename__ = "meeting_periodic_summaries"
    __table_args__ = (
        Index("idx_meeting_periodic_user_meeting_ts", "user_id", "meeting_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False, default="legacy")
    meeting_id = Column(String, index=True)
    summary = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PasswordResetToken(Base):
    """Password reset token with expiry and single use."""

    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        Index("idx_reset_user_expires", "user_id", "expires_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    token_hash = Column(String, nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DocIngestionJob(Base):
    """Track document ingestion tasks."""

    __tablename__ = "doc_ingestion_jobs"
    __table_args__ = (
        Index("idx_doc_jobs_user_created", "user_id", "created_at"),
    )

    id = Column(String, primary_key=True, index=True)  # UUID
    user_id = Column(String, index=True, nullable=False)
    filename = Column(String, nullable=False)
    tab_id = Column(String, index=True, nullable=True)
    status = Column(String, nullable=False, default="queued")  # queued | processing | completed | failed
    chunks_ingested = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MeetingSession(Base):
    """Active meeting session for reconnect (multi-worker safe)."""

    __tablename__ = "meeting_sessions"
    __table_args__ = (
        Index("idx_meeting_session_user", "user_id"),
    )

    user_id = Column(String, primary_key=True)
    meeting_id = Column(String, nullable=False)
    last_seen = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    active = Column(Integer, nullable=False, default=1)  # 1 active, 0 stopped




def _derive_title(summary: str | None, started_at: "datetime | str | None" = None) -> str:
    """Derive a short human-readable title (≤80 chars) from a meeting summary or timestamp."""
    if summary:
        # 1. Prefer a meaningful markdown heading over boilerplate section labels.
        for line in summary.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                heading = " ".join(stripped[3:].split()).strip(" -*•\t\r\n:;.,")
                if heading and heading.lower() not in {
                    "overview",
                    "meeting overview",
                    "summary",
                    "meeting summary",
                    "final summary",
                    "recap",
                    "notes",
                    "agenda",
                }:
                    return heading[:80]

        # 2. Fall back to the first substantive content line.
        import re as _re

        for line in summary.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            stripped = stripped.lstrip("-*• ").strip()
            if not stripped:
                continue
            candidate = " ".join(_re.split(r"[.!?]", stripped, maxsplit=1)[0].split()).strip(
                " -*•\t\r\n:;.,"
            )
            if candidate and candidate.lower() not in {
                "overview",
                "meeting overview",
                "summary",
                "meeting summary",
                "final summary",
                "recap",
                "notes",
                "agenda",
            }:
                return candidate[:80]

        # 3. Use the first sentence from the summary as a last summary-based fallback.
        sentence = " ".join(_re.split(r"[.!?]", summary, maxsplit=1)[0].split()).strip(" -*•\t\r\n:;.,")
        if sentence:
            return sentence[:80]

    # 4. Fall back to formatted timestamp
    if started_at is not None:
        if isinstance(started_at, str):
            try:
                started_at = datetime.fromisoformat(started_at)
            except ValueError:
                return f"Meeting on {started_at}"[:80]
        return f"Meeting on {started_at.strftime('%b %d, %Y at %I:%M %p')}"
    # 4. Ultimate fallback
    return "Untitled Meeting"


async def init_db() -> None:
    """Create all tables if they do not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add tab_id columns if missing
        try:
            await conn.execute(
                text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS tab_id VARCHAR")
            )
        except Exception:
            try:
                await conn.execute(text("ALTER TABLE chat_messages ADD COLUMN tab_id VARCHAR"))
            except Exception:
                pass

        # Add tab_id column to doc_ingestion_jobs if missing (Postgres/SQLite tolerant)
        try:
            await conn.execute(
                text(
                    "ALTER TABLE doc_ingestion_jobs "
                    "ADD COLUMN IF NOT EXISTS tab_id VARCHAR"
                )
            )
        except Exception:
            # SQLite older versions don't support IF NOT EXISTS; try plain add
            try:
                await conn.execute(
                    text("ALTER TABLE doc_ingestion_jobs ADD COLUMN tab_id VARCHAR")
                )
            except Exception:
                pass

        # Add meeting_title column to meeting_summaries if missing
        try:
            await conn.execute(
                text("ALTER TABLE meeting_summaries ADD COLUMN IF NOT EXISTS meeting_title VARCHAR(80)")
            )
        except Exception:
            try:
                await conn.execute(
                    text("ALTER TABLE meeting_summaries ADD COLUMN meeting_title VARCHAR(80)")
                )
            except Exception:
                pass

    await prune_expired_reset_tokens()
    await prune_old_doc_jobs()
    try:
        await prune_old_meetings(_settings.meeting_retention_days)
    except Exception:
        pass




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


async def update_user_password(email: str, password_hash: str) -> None:
    """Update a user's password hash."""
    async with SessionLocal() as session:
        await session.execute(
            text("UPDATE users SET password_hash = :pwd WHERE email = :email"),
            {"pwd": password_hash, "email": email},
        )
        await session.commit()




async def create_doc_job(user_id: str, filename: str, tab_id: str | None = None) -> str:
    """Create a new doc ingestion job and return its id."""
    job_id = str(uuid4())
    async with SessionLocal() as session:
        session.add(
            DocIngestionJob(
                id=job_id,
                user_id=user_id,
                filename=filename,
                tab_id=tab_id,
                status="queued",
            )
        )
        await session.commit()
    return job_id


async def update_doc_job(
    job_id: str,
    *,
    status: str,
    chunks_ingested: int | None = None,
    error: str | None = None,
) -> None:
    async with SessionLocal() as session:
        await session.execute(
            text(
                "UPDATE doc_ingestion_jobs "
                "SET status = :status, chunks_ingested = :chunks, error = :error, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = :id"
            ),
            {
                "status": status,
                "chunks": chunks_ingested,
                "error": error,
                "id": job_id,
            },
        )
        await session.commit()


async def get_doc_job(job_id: str) -> dict | None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(DocIngestionJob).where(DocIngestionJob.id == job_id)
        )
        job = result.scalars().first()
        if not job:
            return None
        return {
            "id": job.id,
            "user_id": job.user_id,
            "filename": job.filename,
            "tab_id": job.tab_id,
            "status": job.status,
            "chunks_ingested": job.chunks_ingested,
            "error": job.error,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        }




async def upsert_meeting_session(user_id: str, meeting_id: str) -> None:
    """Create/update active meeting session with heartbeat."""
    async with SessionLocal() as session:
        await session.execute(
            text(
                """
                INSERT INTO meeting_sessions (user_id, meeting_id, last_seen, active)
                VALUES (:uid, :mid, :now, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    meeting_id=excluded.meeting_id,
                    last_seen=excluded.last_seen,
                    active=1
                """
            ),
            {"uid": user_id, "mid": meeting_id, "now": datetime.now(timezone.utc)},
        )
        await session.commit()


async def get_active_meeting(user_id: str, max_age_minutes: int = 10) -> str | None:
    """Return meeting_id if active and recent."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    async with SessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT meeting_id FROM meeting_sessions
                WHERE user_id = :uid AND active = 1 AND last_seen >= :cutoff
                """
            ),
            {"uid": user_id, "cutoff": cutoff},
        )
        row = result.fetchone()
        return row[0] if row else None


async def mark_meeting_stopped(user_id: str) -> None:
    async with SessionLocal() as session:
        await session.execute(
            text("UPDATE meeting_sessions SET active = 0 WHERE user_id = :uid"),
            {"uid": user_id},
        )
        await session.commit()


async def prune_expired_reset_tokens() -> None:
    """Delete expired or stale reset tokens."""
    async with SessionLocal() as session:
        await session.execute(
            text(
                "DELETE FROM password_reset_tokens "
                "WHERE expires_at < :now OR (used_at IS NOT NULL AND used_at < :week_ago)"
            ),
            {
                "now": datetime.now(timezone.utc),
                "week_ago": datetime.now(timezone.utc) - timedelta(days=7),
            },
        )
        await session.commit()


async def prune_old_doc_jobs(days: int = 14) -> None:
    """Delete old ingestion jobs to keep table size bounded."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with SessionLocal() as session:
        await session.execute(
            text("DELETE FROM doc_ingestion_jobs WHERE updated_at < :cutoff"),
            {"cutoff": cutoff},
        )
        await session.commit()





def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_reset_token(user_id: str, ttl_hours: int = 1) -> str:
    """Create and store a password reset token; returns the raw token."""
    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

    async with SessionLocal() as session:
        session.add(
            PasswordResetToken(
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
        )
        await session.commit()
    return token


async def validate_reset_token(raw_token: str) -> User | None:
    """Return the associated user if token is valid, unexpired, and unused."""
    token_hash = _hash_token(raw_token)
    async with SessionLocal() as session:
        result = await session.execute(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        )
        record: PasswordResetToken | None = result.scalars().first()
        if (
            record
            and record.used_at is None
            and record.expires_at > datetime.now(timezone.utc)
        ):
            user_result = await session.execute(
                select(User).where(User.email == record.user_id)
            )
            return user_result.scalars().first()
    return None


async def mark_reset_token_used(raw_token: str) -> None:
    """Mark a reset token as used."""
    token_hash = _hash_token(raw_token)
    async with SessionLocal() as session:
        await session.execute(
            text(
                "UPDATE password_reset_tokens "
                "SET used_at = :used_at "
                "WHERE token_hash = :token_hash"
            ),
            {"used_at": datetime.now(timezone.utc), "token_hash": token_hash},
        )
        await session.commit()





async def add_message(user_id: str, role: str, content: str, tab_id: str | None = None) -> None:
    """Persist a chat message."""
    async with SessionLocal() as session:
        session.add(
            ChatMessage(
                user_id=user_id,
                tab_id=tab_id,
                role=role,
                content=content,
                timestamp=time.time(),
            )
        )
        await session.commit()


async def get_recent_history(user_id: str, limit: int = 5, tab_id: str | None = None) -> list[dict[str, str]]:
    """Return the last *limit* messages for a user (and tab if provided), oldest first."""
    async with SessionLocal() as session:
        stmt = select(ChatMessage).where(ChatMessage.user_id == user_id)
        if tab_id is not None:
            stmt = stmt.where(ChatMessage.tab_id == tab_id)
        stmt = stmt.order_by(ChatMessage.timestamp.desc()).limit(limit)
        result = await session.execute(
            stmt
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





async def save_meeting_chunk(user_id: str, meeting_id: str, text_content: str) -> tuple[int, datetime]:
    """
    Append a transcript chunk to a meeting.

    Returns:
        (chunk_id, timestamp) for sequencing and embeddings.
    """
    now_ts = datetime.now(timezone.utc)
    encrypted = encrypt_text(text_content, ENCRYPTION_KEY)
    async with SessionLocal() as session:
        record = MeetingTranscript(
            user_id=user_id,
            meeting_id=meeting_id,
            text=encrypted,
            timestamp=now_ts,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record.id, now_ts


async def save_meeting_summary(user_id: str, meeting_id: str, summary: str) -> None:
    """Create or update the summary for a meeting."""
    encrypted = encrypt_text(summary, ENCRYPTION_KEY)
    async with SessionLocal() as session:
        existing = await session.execute(
            text(
                "SELECT id FROM meeting_summaries "
                "WHERE user_id = :uid AND meeting_id = :mid"
            ),
            {"uid": user_id, "mid": meeting_id},
        )
        row = existing.fetchone()
        if row:
            await session.execute(
                text(
                    "UPDATE meeting_summaries SET summary = :summary "
                    "WHERE user_id = :uid AND meeting_id = :mid"
                ),
                {"summary": encrypted, "uid": user_id, "mid": meeting_id},
            )
        else:
            session.add(
                MeetingSummary(
                    user_id=user_id,
                    meeting_id=meeting_id,
                    summary=encrypted,
                )
            )
        await session.commit()


async def save_meeting_title(user_id: str, meeting_id: str, title: str) -> None:
    """Update the meeting_title for an existing meeting_summaries row (no-op if row absent)."""
    async with SessionLocal() as session:
        await session.execute(
            text(
                "UPDATE meeting_summaries SET meeting_title = :title "
                "WHERE user_id = :uid AND meeting_id = :mid"
            ),
            {"title": title[:80], "uid": user_id, "mid": meeting_id},
        )
        await session.commit()


async def get_meeting_title(user_id: str, meeting_id: str) -> str:
    """Return the stored title for a meeting, falling back to _derive_title."""
    async with SessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT ms.meeting_title, MIN(mt.timestamp) as started_at "
                "FROM meeting_summaries ms "
                "LEFT JOIN meeting_transcripts mt ON ms.user_id = mt.user_id AND ms.meeting_id = mt.meeting_id "
                "WHERE ms.user_id = :uid AND ms.meeting_id = :mid "
                "GROUP BY ms.meeting_title"
            ),
            {"uid": user_id, "mid": meeting_id},
        )
        row = result.fetchone()
        if row and row[0]:
            return row[0]
        started_at = str(row[1]) if row and row[1] else None
        return _derive_title(None, started_at)


async def save_periodic_summary(user_id: str, meeting_id: str, summary: str) -> None:
    """Persist a periodic (in-meeting) summary snapshot."""
    encrypted = encrypt_text(summary, ENCRYPTION_KEY)
    async with SessionLocal() as session:
        session.add(
            MeetingPeriodicSummary(
                user_id=user_id,
                meeting_id=meeting_id,
                summary=encrypted,
            )
        )
        await session.commit()


async def get_meeting_summary(user_id: str, meeting_id: str) -> str | None:
    """Retrieve the summary for a meeting."""
    async with SessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT summary FROM meeting_summaries "
                "WHERE user_id = :uid AND meeting_id = :mid"
            ),
            {"uid": user_id, "mid": meeting_id},
        )
        row = result.fetchone()
        return decrypt_text(row[0], ENCRYPTION_KEY) if row else None


async def get_meeting_transcript(user_id: str, meeting_id: str) -> str:
    """Retrieve the full concatenated transcript for a meeting."""
    async with SessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT text FROM meeting_transcripts "
                "WHERE user_id = :uid AND meeting_id = :mid ORDER BY id ASC"
            ),
            {"uid": user_id, "mid": meeting_id},
        )
        rows = result.fetchall()
        parts: list[str] = []
        for row in rows:
            parts.append(decrypt_text(row[0], ENCRYPTION_KEY))
        return "\n".join(p for p in parts if p)


async def get_recent_transcript_window(
    user_id: str,
    meeting_id: str,
    minutes: int,
    max_chunks: int = 200,
) -> str:
    """Return transcript text within the last `minutes`, ordered chronologically."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    async with SessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT text FROM meeting_transcripts "
                "WHERE user_id = :uid AND meeting_id = :mid AND timestamp >= :cutoff "
                "ORDER BY id ASC LIMIT :limit"
            ),
            {"uid": user_id, "mid": meeting_id, "cutoff": cutoff, "limit": max_chunks},
        )
        rows = result.fetchall()
        return "\n".join(
            decrypt_text(row[0], ENCRYPTION_KEY) for row in rows if row and row[0]
        )


async def list_meetings(user_id: str, limit: int = 50) -> list[dict]:
    """Return a list of recent meetings with their metadata."""
    async with SessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT mt.meeting_id, MIN(mt.timestamp) as started_at, ms.meeting_title "
                "FROM meeting_transcripts mt "
                "LEFT JOIN meeting_summaries ms ON mt.user_id = ms.user_id AND mt.meeting_id = ms.meeting_id "
                "WHERE mt.user_id = :uid "
                "GROUP BY mt.meeting_id, ms.meeting_title "
                "ORDER BY started_at DESC "
                "LIMIT :limit"
            ),
            {"uid": user_id, "limit": limit},
        )
        rows = result.fetchall()
        meetings = []
        for row in rows:
            meeting_id, started_at_raw, meeting_title = row[0], row[1], row[2]
            started_at_str = str(started_at_raw) if started_at_raw else None
            has_summary = await get_meeting_summary(user_id, meeting_id)
            if meeting_title:
                title = meeting_title
            else:
                title = _derive_title(None, started_at_str)
            meetings.append(
                {
                    "meeting_id": meeting_id,
                    "started_at": started_at_str,
                    "has_summary": has_summary is not None,
                    "title": title,
                }
            )
        return meetings


async def delete_meeting_data(user_id: str, meeting_id: str) -> None:
    """Hard delete all meeting-related records for the user/meeting."""
    async with SessionLocal() as session:
        await session.execute(
            text("DELETE FROM meeting_transcripts WHERE user_id = :uid AND meeting_id = :mid"),
            {"uid": user_id, "mid": meeting_id},
        )
        await session.execute(
            text("DELETE FROM meeting_periodic_summaries WHERE user_id = :uid AND meeting_id = :mid"),
            {"uid": user_id, "mid": meeting_id},
        )
        await session.execute(
            text("DELETE FROM meeting_summaries WHERE user_id = :uid AND meeting_id = :mid"),
            {"uid": user_id, "mid": meeting_id},
        )
        await session.execute(
            text("DELETE FROM meeting_sessions WHERE user_id = :uid AND meeting_id = :mid"),
            {"uid": user_id, "mid": meeting_id},
        )
        await session.commit()


async def prune_old_meetings(retention_days: int) -> None:
    """Delete meeting data older than the retention window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    async with SessionLocal() as session:
        await session.execute(
            text("DELETE FROM meeting_transcripts WHERE timestamp < :cutoff"),
            {"cutoff": cutoff},
        )
        await session.execute(
            text("DELETE FROM meeting_periodic_summaries WHERE created_at < :cutoff"),
            {"cutoff": cutoff},
        )
        await session.execute(
            text("DELETE FROM meeting_summaries WHERE created_at < :cutoff"),
            {"cutoff": cutoff},
        )
        await session.execute(
            text("DELETE FROM meeting_sessions WHERE last_seen < :cutoff"),
            {"cutoff": cutoff},
        )
        await session.commit()
    # Also prune vector embeddings
    try:
        prune_old_meeting_embeddings(retention_days)
    except Exception:
        pass
