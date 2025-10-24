import time
from sqlalchemy.future import select
from app.db.chat_memory_db import SessionLocal, ChatMessage, Base, engine

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
