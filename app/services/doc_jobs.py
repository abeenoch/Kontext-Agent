import asyncio
from typing import Callable

from app.services.chat_memory import (
    create_doc_job,
    update_doc_job,
    get_doc_job,
)
from app.services.rag_pipeline import ingest_file
from app.logger import get_logger

logger = get_logger(__name__)


async def process_doc_job(job_id: str, user_id: str, filename: str, content: bytes) -> None:
    """Run the ingestion job and update status."""
    try:
        await update_doc_job(job_id, status="processing")
        chunks = await ingest_file(user_id, filename, content)
        await update_doc_job(job_id, status="completed", chunks_ingested=chunks)
        logger.info("Doc job %s completed (%d chunks)", job_id, chunks)
    except Exception as exc:
        logger.error("Doc job %s failed: %s", job_id, exc, exc_info=True)
        await update_doc_job(job_id, status="failed", error=str(exc))


async def get_job(job_id: str, user_id: str) -> dict | None:
    """Return job info if it belongs to the user."""
    job = await get_doc_job(job_id)
    if job and job["user_id"] == user_id:
        return job
    return None
