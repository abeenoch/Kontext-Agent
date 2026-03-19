import asyncio
import re
import time
from typing import Dict, List, Optional

import chromadb

from app.config import get_settings
from app.logger import get_logger
from app.utils.embedding_utils import get_embedding

logger = get_logger(__name__)
settings = get_settings()

# Single persistent client shared across the app
_client = chromadb.PersistentClient(path=settings.chroma_dir)




_SAFE_PATTERN = re.compile(r"[^a-zA-Z0-9_-]")


def _slugify(user_id: str) -> str:
    """Sanitize user identifier for collection names."""
    return _SAFE_PATTERN.sub("_", user_id)


def docs_collection_name(user_id: str) -> str:
    return f"docs_{_slugify(user_id)}"


def meetings_collection_name(user_id: str) -> str:
    return f"meetings_{_slugify(user_id)}"


def legacy_docs_collection_name(user_id: str) -> str:
    """Legacy name used in earlier versions; kept for backwards compatibility."""
    return f"user_{_slugify(user_id)}"





def _get_or_create(name: str):
    return _client.get_or_create_collection(name=name)


def _maybe_get(name: str):
    try:
        return _client.get_collection(name=name)
    except Exception:
        return None


async def ensure_user_collections(user_id: str) -> None:
    """Create docs + meetings collections for a user if missing."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: (
            _get_or_create(docs_collection_name(user_id)),
            _get_or_create(meetings_collection_name(user_id)),
        ),
    )


def get_docs_collection(user_id: str):
    """
    Return the docs collection for a user, falling back to the legacy name
    if it still contains data.
    """
    new_col = _get_or_create(docs_collection_name(user_id))
    try:
        if new_col.count() > 0:
            return new_col
    except Exception:
        pass

    legacy = _maybe_get(legacy_docs_collection_name(user_id))
    if legacy:
        try:
            if legacy.count() > 0:
                return legacy
        except Exception:
            pass
    return new_col


def get_meetings_collection(user_id: str):
    return _get_or_create(meetings_collection_name(user_id))


async def clear_docs_collection(user_id: str) -> None:
    """Delete docs collections (new + legacy) for a user."""
    loop = asyncio.get_running_loop()

    def _delete():
        for name in {
            docs_collection_name(user_id),
            legacy_docs_collection_name(user_id),
        }:
            try:
                _client.delete_collection(name=name)
            except Exception:
                continue

    await loop.run_in_executor(None, _delete)




async def add_meeting_chunk_embedding(
    user_id: str,
    meeting_id: str,
    text: str,
    *,
    speaker: str | None = None,
    chunk_index: Optional[int] = None,
    created_at: Optional[float] = None,
) -> None:
    """Embed and store an individual meeting transcript chunk."""
    if not text or not text.strip():
        return

    loop = asyncio.get_running_loop()
    embedding = await loop.run_in_executor(None, get_embedding, text)

    ts = created_at if created_at is not None else time.time()
    chunk_id = f"{meeting_id}_{int(ts * 1000)}"
    metadata: Dict[str, str | int | float | None] = {
        "meeting_id": meeting_id,
        "user_id": user_id,
        "kind": "chunk",
        "chunk_index": chunk_index if chunk_index is not None else int(ts * 1000),
        "timestamp": ts,
    }
    if speaker:
        metadata["speaker"] = speaker

    collection = get_meetings_collection(user_id)
    await loop.run_in_executor(
        None,
        lambda: collection.upsert(
            ids=[chunk_id],
            documents=[text],
            embeddings=[embedding.tolist()],
            metadatas=[metadata],
        ),
    )


async def add_meeting_summary_embedding(
    user_id: str, meeting_id: str, summary_text: str
) -> None:
    """Embed and store the final meeting summary."""
    if not summary_text or not summary_text.strip():
        return

    loop = asyncio.get_running_loop()
    embedding = await loop.run_in_executor(None, get_embedding, summary_text)

    ts = time.time()
    collection = get_meetings_collection(user_id)
    await loop.run_in_executor(
        None,
        lambda: collection.upsert(
            ids=[f"{meeting_id}_final_summary"],
            documents=[summary_text],
            embeddings=[embedding.tolist()],
            metadatas=[
                {
                    "meeting_id": meeting_id,
                    "user_id": user_id,
                    "kind": "final_summary",
                    "timestamp": ts,
                }
            ],
        ),
    )


async def query_meetings(
    user_id: str,
    query: str,
    *,
    meeting_id: Optional[str] = None,
    after_ts: Optional[float] = None,
    before_ts: Optional[float] = None,
    n_results: int = 5,
) -> List[str]:
    """Semantic search over meeting transcripts/summaries with optional filters."""
    if not query or not query.strip():
        return []

    collection = get_meetings_collection(user_id)
    if collection.count() == 0:
        return []

    loop = asyncio.get_running_loop()
    query_embedding = await loop.run_in_executor(None, get_embedding, query)

    where: Dict[str, object] = {}
    if meeting_id:
        where["meeting_id"] = meeting_id
    ts_filter: Dict[str, float] = {}
    if after_ts is not None:
        ts_filter["$gt"] = after_ts
    if before_ts is not None:
        ts_filter["$lt"] = before_ts
    if ts_filter:
        where["timestamp"] = ts_filter

    try:
        results = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=min(n_results, max(1, collection.count())),
            where=where or None,
        )
        return results.get("documents", [[]])[0]
    except Exception as exc:
        logger.warning("Meeting query failed: %s", exc)
        return []
