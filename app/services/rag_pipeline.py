import asyncio
import re
from datetime import datetime

import pdfplumber

from app.utils.text_splitter import split_text
from app.utils.embedding_utils import get_embedding
from app.config import get_settings
from app.logger import get_logger
from app.services.vector_store import get_docs_collection, clear_docs_collection

logger = get_logger(__name__)
settings = get_settings()


async def ingest_file(user_id: str, tab_id: str, filename: str, content: bytes) -> int:
    """
    Ingest a document into the RAG vector store.

    Supports PDF and TXT files.

    Args:
        user_id: Owner of the document.
        filename: Original filename (used to detect format).
        content: Raw file bytes.

    Returns:
        Number of chunks ingested.
    """
    loop = asyncio.get_running_loop()

    # Extract text
    ext = filename.lower().rsplit(".", maxsplit=1)[-1]

    if ext == "pdf":
        raw_text = await loop.run_in_executor(None, _extract_pdf_text, content)
    elif ext == "txt":
        raw_text = content.decode("utf-8", errors="replace")
    else:
        raise ValueError(f"Unsupported file type: .{ext}")

    text = _normalize_text(raw_text)

    if not text or not text.strip():
        logger.warning("No text extracted from %s", filename)
        return 0

    # Split into chunks
    chunks = split_text(
        text,
        chunk_size=settings.chunk_size,
        overlap=settings.chunk_overlap,
    )

    if not chunks:
        return 0

    # Embed and store
    collection = get_docs_collection(user_id, tab_id)
    uploaded_at = datetime.utcnow().timestamp()

    for i, chunk in enumerate(chunks):
        chunk_id = f"{filename}__chunk_{i}"
        embedding = await loop.run_in_executor(None, get_embedding, chunk)
        collection.upsert(
            ids=[chunk_id],
            documents=[chunk],
            embeddings=[embedding.tolist()],
            metadatas=[
                {
                    "filename": filename,
                    "chunk_index": i,
                    "user_id": user_id,
                    "tab_id": tab_id,
                    "uploaded_at": uploaded_at,
                }
            ],
        )

    logger.info("Ingested %d chunks from %s for user %s", len(chunks), filename, user_id)
    return len(chunks)


def list_user_docs(user_id: str, tab_id: str, limit: int = 20) -> list[dict]:
    """
    Return up to `limit` document descriptors for a user, sorted by latest upload.

    Each item: {"filename": str, "uploaded_at": float}.
    """
    collection = get_docs_collection(user_id, tab_id)
    try:
        data = collection.get(include=["metadatas"])
    except Exception:
        return []

    docs = []
    for batch in data.get("metadatas", []):
        for meta in batch:
            if not isinstance(meta, dict):
                continue
            filename = meta.get("filename")
            uploaded_at = meta.get("uploaded_at") or 0
            if filename:
                docs.append({"filename": filename, "uploaded_at": uploaded_at})

    # De-duplicate by filename, keep latest timestamp
    dedup: dict[str, float] = {}
    for item in docs:
        ts = item["uploaded_at"]
        fname = item["filename"]
        if fname not in dedup or ts > dedup[fname]:
            dedup[fname] = ts

    sorted_docs = sorted(
        [{"filename": k, "uploaded_at": v} for k, v in dedup.items()],
        key=lambda x: (-x["uploaded_at"], x["filename"]),
    )
    return sorted_docs[:limit]


def _extract_pdf_text(content: bytes) -> str:
    """Extract text from a PDF file."""
    import io

    text_parts = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


async def retrieve_docs(
    user_id: str,
    tab_id: str,
    query: str,
    n_results: int = 3,
) -> list[str]:
    """
    Retrieve relevant document chunks for a query.

    Args:
        user_id: Owner of the documents.
        query: The search query.
        n_results: Maximum number of chunks to return.

    Returns:
        List of relevant text chunks, possibly empty.
    """
    try:
        loop = asyncio.get_running_loop()
        collection = get_docs_collection(user_id, tab_id)

        # Check if collection has any documents
        if collection.count() == 0:
            return []

        # Heuristic: if the query references recency, bias retrieval to the latest upload
        ql = query.lower()
        prefer_latest = any(
            phrase in ql
            for phrase in (
                "last",
                "latest",
                "most recent",
                "recent upload",
                "recently uploaded",
                "just uploaded",
                "newest",
            )
        )

        query_embedding = await loop.run_in_executor(None, get_embedding, query)

        results = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=min(max(n_results, 5), max(1, collection.count())),
            include=["documents", "metadatas"],
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        if prefer_latest and metadatas:
            max_uploaded = None
            for meta in metadatas:
                ua = meta.get("uploaded_at")
                if ua is not None and (max_uploaded is None or ua > max_uploaded):
                    max_uploaded = ua
            if max_uploaded is not None:
                filtered = [
                    doc for doc, meta in zip(documents, metadatas)
                    if meta.get("uploaded_at") == max_uploaded
                ]
                if filtered:
                    documents = filtered

        # Fallback: if nothing matched, return the most recently uploaded chunks
        if not documents:
            try:
                data = collection.get(include=["documents", "metadatas"])
                docs_flat = []
                metas_flat = []
                for batch_docs, batch_metas in zip(
                    data.get("documents", []), data.get("metadatas", [])
                ):
                    docs_flat.extend(batch_docs)
                    metas_flat.extend(batch_metas)

                if metas_flat and docs_flat:
                    # Pair and sort by uploaded_at desc, then chunk_index asc
                    paired = []
                    for d, m in zip(docs_flat, metas_flat):
                        paired.append(
                            (
                                m.get("uploaded_at") or 0,
                                m.get("chunk_index") or 0,
                                d,
                            )
                        )
                    paired.sort(key=lambda x: (-x[0], x[1]))
                    documents = [p[2] for p in paired[:n_results]]
            except Exception as exc:
                logger.debug("Latest-doc fallback failed: %s", exc)

        return documents

    except Exception as exc:
        logger.error("RAG retrieval error: %s", exc, exc_info=True)
        return []


def _normalize_text(text: str) -> str:
    """Lightweight cleanup to strip HTML-ish tags and normalize whitespace."""
    if not text:
        return ""
    cleaned = text.replace("\r", "\n")
    # Preserve block structure as newlines
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</(p|div|li|tr|th|td)>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<(p|div|li|tr|th|td)[^>]*>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)  # remove residual tags
    cleaned = cleaned.replace("\u00a0", " ")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n\s*\n+", "\n\n", cleaned)
    return cleaned.strip()


async def clear_user_docs(user_id: str, tab_id: str) -> None:
    """Delete all documents for a user from the vector store for the given tab."""
    try:
        await clear_docs_collection(user_id, tab_id)
        logger.info("Cleared documents for user %s tab %s", user_id, tab_id)
    except Exception as exc:
        logger.warning("Error clearing docs for %s tab %s: %s", user_id, tab_id, exc)
