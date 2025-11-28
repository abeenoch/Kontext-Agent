import aiosqlite
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
import json
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class Database:
    """Async SQLite database manager."""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
    async def init_schema(self):
        """Initialize database schema."""
        async with aiosqlite.connect(self.db_path) as db:
            # Meetings table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS meetings (
                    meeting_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    participants TEXT,
                    status TEXT NOT NULL DEFAULT 'recording',
                    started_at TEXT NOT NULL,
                    ended_at TEXT
                )
            """)
            
            # Transcripts table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS transcripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meeting_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    speaker TEXT,
                    FOREIGN KEY (meeting_id) REFERENCES meetings (meeting_id)
                )
            """)
            
            # Summaries table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meeting_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    is_final INTEGER NOT NULL DEFAULT 0,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (meeting_id) REFERENCES meetings (meeting_id)
                )
            """)
            
            # Chat messages table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meeting_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (meeting_id) REFERENCES meetings (meeting_id)
                )
            """)
            
            # Integration logs table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS integration_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meeting_id TEXT NOT NULL,
                    integration_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (meeting_id) REFERENCES meetings (meeting_id)
                )
            """)
            
            # Create indexes
            await db.execute("CREATE INDEX IF NOT EXISTS idx_transcripts_meeting ON transcripts(meeting_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_summaries_meeting ON summaries(meeting_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_chat_meeting ON chat_messages(meeting_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_integrations_meeting ON integration_logs(meeting_id)")
            
            await db.commit()
            logger.info("Database schema initialized")
    
    async def close(self):
        """Close database connections (placeholder for cleanup)."""
        logger.info("Database closed")
    

    async def create_meeting(self, meeting_id: str, title: str, participants: List[str]) -> None:
        """Create a new meeting record."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO meetings (meeting_id, title, participants, started_at, status) VALUES (?, ?, ?, ?, ?)",
                (meeting_id, title, json.dumps(participants), datetime.utcnow().isoformat(), "recording")
            )
            await db.commit()
        logger.info(f"Created meeting {meeting_id}")
    
    async def get_meeting(self, meeting_id: str) -> Optional[Dict[str, Any]]:
        """Get meeting by ID."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    """
                    SELECT meeting_id, title, participants, status, started_at, ended_at
                    FROM meetings
                    WHERE meeting_id = ?
                    """,
                    (meeting_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        participants = row["participants"]
                        if isinstance(participants, str):
                            try:
                                participants = json.loads(participants)
                            except:
                                participants = []
                        
                        return {
                            "meeting_id": row["meeting_id"],
                            "title": row["title"],
                            "participants": participants,
                            "status": row["status"],
                            "started_at": row["started_at"],
                            "ended_at": row["ended_at"]
                        }
                    return None
        except Exception as e:
            logger.error(f"Error getting meeting {meeting_id}: {e}", exc_info=True)
            return None
    
    async def update_meeting_status(self, meeting_id: str, status: str, end_time: datetime = None) -> None:
        """Update meeting status."""
        async with aiosqlite.connect(self.db_path) as db:
            if end_time:
                await db.execute(
                    "UPDATE meetings SET status = ?, ended_at = ? WHERE meeting_id = ?",
                    (status, end_time.isoformat(), meeting_id)
                )
            else:
                await db.execute(
                    "UPDATE meetings SET status = ? WHERE meeting_id = ?",
                    (status, meeting_id)
                )
            await db.commit()
        logger.info(f"Updated meeting {meeting_id} status to {status}")
    
    async def list_meetings(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List recent meetings."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    """
                    SELECT meeting_id, title, participants, status, started_at, ended_at
                    FROM meetings
                    ORDER BY started_at DESC
                    LIMIT ?
                    """,
                    (limit,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    result = []
                    for row in rows:
                        participants = row["participants"]
                        if isinstance(participants, str):
                            try:
                                participants = json.loads(participants)
                            except:
                                participants = []
                        
                        result.append({
                            "meeting_id": row["meeting_id"],
                            "title": row["title"],
                            "participants": participants,
                            "status": row["status"],
                            "started_at": row["started_at"],
                            "ended_at": row["ended_at"]
                        })
                    return result
        except Exception as e:
            logger.error(f"Error listing meetings: {e}", exc_info=True)
            return []
    

    
    async def add_transcript(self, meeting_id: str, text: str) -> None:
        """Add transcript chunk."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO transcripts (meeting_id, text, timestamp) VALUES (?, ?, ?)",
                (meeting_id, text, datetime.utcnow().isoformat())
            )
            await db.commit()
    
    async def get_all_transcripts(self, meeting_id: str) -> List[Dict[str, Any]]:
        """Get all transcript segments for a meeting."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    """
                    SELECT id, meeting_id, text, timestamp, speaker
                    FROM transcripts
                    WHERE meeting_id = ?
                    ORDER BY timestamp ASC
                    """,
                    (meeting_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [
                        {
                            "id": row["id"],
                            "meeting_id": row["meeting_id"],
                            "text": row["text"],
                            "timestamp": row["timestamp"],
                            "speaker": row["speaker"]
                        }
                        for row in rows
                    ]
        except Exception as e:
            logger.error(f"Error getting transcripts for {meeting_id}: {e}", exc_info=True)
            return []
    
    async def get_full_transcript(self, meeting_id: str) -> str:
        """Get complete meeting transcript as single string."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT text FROM transcripts WHERE meeting_id = ? ORDER BY timestamp",
                    (meeting_id,)
                )
                rows = await cursor.fetchall()
                return " ".join([row[0] for row in rows])
        except Exception as e:
            logger.error(f"Error getting full transcript: {e}", exc_info=True)
            return ""
    

    
    async def add_summary(self, meeting_id: str, summary: Dict[str, Any], is_final: bool = False) -> None:
        """Add summary (periodic or final)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO summaries (meeting_id, summary, is_final, timestamp) VALUES (?, ?, ?, ?)",
                (meeting_id, json.dumps(summary), 1 if is_final else 0, datetime.utcnow().isoformat())
            )
            await db.commit()
    
    async def get_all_summaries(self, meeting_id: str) -> List[Dict[str, Any]]:
        """Get all summaries for a meeting."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    """
                    SELECT id, meeting_id, summary, is_final, timestamp
                    FROM summaries
                    WHERE meeting_id = ?
                    ORDER BY timestamp ASC
                    """,
                    (meeting_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    result = []
                    for row in rows:
                        summary_data = row["summary"]
                        if isinstance(summary_data, str):
                            try:
                                summary_data = json.loads(summary_data)
                            except:
                                summary_data = {"overview": summary_data}
                        
                        result.append({
                            "id": row["id"],
                            "meeting_id": row["meeting_id"],
                            "summary": summary_data,
                            "is_final": bool(row["is_final"]),
                            "timestamp": row["timestamp"]
                        })
                    return result
        except Exception as e:
            logger.error(f"Error getting summaries for {meeting_id}: {e}", exc_info=True)
            return []
    
    async def get_final_summary(self, meeting_id: str) -> Optional[Dict[str, Any]]:
        """Get the final summary for a meeting (if exists)."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    """
                    SELECT summary
                    FROM summaries
                    WHERE meeting_id = ? AND is_final = 1
                    ORDER BY timestamp DESC
                    LIMIT 1
                    """,
                    (meeting_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        summary_data = row["summary"]
                        if isinstance(summary_data, str):
                            try:
                                return json.loads(summary_data)
                            except:
                                return {"overview": summary_data}
                        return summary_data
                    return None
        except Exception as e:
            logger.error(f"Error getting final summary for {meeting_id}: {e}", exc_info=True)
            return None
    

    
    async def add_chat_message(self, meeting_id: str, role: str, content: str):
        """Add a chat message."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO chat_messages (meeting_id, role, content, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    (meeting_id, role, content, datetime.utcnow().isoformat())
                )
                await db.commit()
            logger.info(f"Added {role} chat message to {meeting_id}")
        except Exception as e:
            logger.error(f"Error adding chat message: {e}", exc_info=True)
    
    async def get_chat_history(self, meeting_id: str) -> List[Dict[str, Any]]:
        """Get chat history for a meeting."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    """
                    SELECT id, meeting_id, role, content, timestamp
                    FROM chat_messages
                    WHERE meeting_id = ?
                    ORDER BY timestamp ASC
                    """,
                    (meeting_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [
                        {
                            "id": row["id"],
                            "meeting_id": row["meeting_id"],
                            "role": row["role"],
                            "content": row["content"],
                            "timestamp": row["timestamp"]
                        }
                        for row in rows
                    ]
        except Exception as e:
            logger.error(f"Error getting chat history for {meeting_id}: {e}", exc_info=True)
            return []
    

    
    async def log_integration(
        self, 
        meeting_id: str, 
        integration_type: str, 
        status: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log integration attempt."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO integration_logs (meeting_id, integration_type, status, details, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        meeting_id,
                        integration_type,
                        status,
                        json.dumps(details) if details else None,
                        datetime.utcnow().isoformat()
                    )
                )
                await db.commit()
            
            logger.info(f"Logged {integration_type} integration for {meeting_id}: {status}")
        except Exception as e:
            logger.error(f"Error logging integration: {e}", exc_info=True)




db = Database()