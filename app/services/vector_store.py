import asyncio
import re
import time
from typing import Dict, List, Optional

# Chroma's telemetry stack imports LogData from opentelemetry.sdk._logs in some versions;
# older/newer opentelemetry builds omit it, which can break startup. Patch in a stub
# before importing chromadb to keep the service bootable.
try:  # pragma: no cover - defensive compatibility shim
    import opentelemetry.sdk._logs as _otel_logs

    if not hasattr(_otel_logs, "LogData"):
        class _LogData:  # minimal placeholder
            pass

        _otel_logs.LogData = _LogData
except Exception:
    pass

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


def docs_collection_name(user_id: str, tab_id: str | None = None) -> str:
    if tab_id:
        return f"docs_{_slugify(user_id)}_{_slugify(tab_id)}"
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


def _chunk_text(text: str, max_chars: int = 800, overlap: int = 120) -> list[str]:
    """Split text into overlapping chunks for embedding."""
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + max_chars)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == n:
            break
        start = max(0, end - overlap)
    return chunks


async def ensure_user_collections(user_id: str, tab_id: str | None = None) -> None:
    """Create docs + meetings collections for a user (and tab) if missing."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: (
            _get_or_create(docs_collection_name(user_id, tab_id)),
            _get_or_create(meetings_collection_name(user_id)),
        ),
    )


def get_docs_collection(user_id: str, tab_id: str | None = None):
    """
    Return the docs collection for a user (and tab), falling back to the legacy name
    if it still contains data.
    """
    new_col = _get_or_create(docs_collection_name(user_id, tab_id))
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


async def clear_docs_collection(user_id: str, tab_id: str | None = None) -> None:
    """Delete docs collections (new + legacy) for a user; if tab_id is None, clear all tabs."""
    loop = asyncio.get_running_loop()

    def _delete():
        names = {
            docs_collection_name(user_id, tab_id),
            legacy_docs_collection_name(user_id),
        }
        if tab_id is None:
            try:
                for col in _client.list_collections():
                    if col.name.startswith(f"docs_{_slugify(user_id)}_"):
                        names.add(col.name)
            except Exception:
                pass
        for name in names:
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
    if settings.app_env == "test":
        return
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
    if settings.app_env == "test":
        return
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


async def add_full_transcript_embeddings(
    user_id: str, meeting_id: str, transcript_text: str
) -> None:
    """
    Embed the full meeting transcript in chunks after the meeting ends.

    This is a safety net — individual chunks are embedded live during the meeting,
    but this guarantees complete coverage regardless of any dropped chunks.
    """
    if settings.app_env == "test":
        return
    if not transcript_text or not transcript_text.strip():
        return

    chunks = _chunk_text(transcript_text)
    if not chunks:
        return

    loop = asyncio.get_running_loop()
    ts = time.time()
    collection = get_meetings_collection(user_id)

    for idx, chunk in enumerate(chunks):
        embedding = await loop.run_in_executor(None, get_embedding, chunk)
        await loop.run_in_executor(
            None,
            lambda c=chunk, e=embedding, i=idx: collection.upsert(
                ids=[f"{meeting_id}_full_{i}"],
                documents=[c],
                embeddings=[e.tolist()],
                metadatas=[
                    {
                        "meeting_id": meeting_id,
                        "user_id": user_id,
                        "kind": "full_transcript",
                        "chunk_index": i,
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
    """Semantic search over meeting transcripts/summaries with optional filters.

    Convenience wrapper around :func:`query_meetings_detailed` that returns only
    the chunk texts.
    """
    items = await query_meetings_detailed(
        user_id,
        query,
        meeting_id=meeting_id,
        after_ts=after_ts,
        before_ts=before_ts,
        n_results=n_results,
    )
    return [item["text"] for item in items]


async def query_meetings_detailed(
    user_id: str,
    query: str,
    *,
    meeting_id: Optional[str] = None,
    after_ts: Optional[float] = None,
    before_ts: Optional[float] = None,
    n_results: int = 5,
) -> List[dict]:
    """Semantic search over meeting transcripts/summaries with optional filters.

    Returns a list of dicts with keys ``text`` and ``meeting_id`` so callers can
    attribute each chunk to its source meeting.
    """
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
        docs = results.get("documents", [[]])[0] or []
        metas = results.get("metadatas", [[]])[0] or []
        items: List[dict] = []
        for doc, meta in zip(docs, metas):
            items.append(
                {
                    "text": doc,
                    "meeting_id": (meta or {}).get("meeting_id"),
                }
            )
        return items
    except Exception as exc:
        logger.warning("Meeting query failed: %s", exc)
        return []


def delete_meeting_embeddings(user_id: str, meeting_id: str) -> None:
    """Remove all embeddings for a specific meeting."""
    collection = get_meetings_collection(user_id)
    try:
        ids = collection.get(where={"meeting_id": meeting_id}).get("ids", [])
        if ids:
            collection.delete(ids=ids)
    except Exception as exc:
        logger.warning("Failed to delete meeting embeddings for %s/%s: %s", user_id, meeting_id, exc)


def prune_old_meeting_embeddings(retention_days: int) -> None:
    """Delete meeting embeddings older than retention window across all users."""
    cutoff_ts = time.time() - retention_days * 86400
    try:
        for col in _client.list_collections():
            if not col.name.startswith("meetings_"):
                continue
            try:
                col_ref = _client.get_collection(col.name)
                data = col_ref.get(where={"timestamp": {"$lt": cutoff_ts}})
                ids = data.get("ids", [])
                if ids:
                    col_ref.delete(ids=ids)
            except Exception as exc:
                logger.debug("Prune failed for collection %s: %s", col.name, exc)
    except Exception as exc:
        logger.debug("Meeting embedding retention sweep failed: %s", exc)
