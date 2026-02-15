"""RAG pipeline -- document ingestion and retrieval via ChromaDB."""

import asyncio
from typing import Optional

import chromadb
import pdfplumber

from app.utils.text_splitter import split_text
from app.utils.embedding_utils import get_embedding
from app.config import get_settings
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Persistent ChromaDB client
_chroma_client = chromadb.PersistentClient(path=settings.chroma_dir)


def _get_collection(user_id: str) -> chromadb.Collection:
    """Get or create a ChromaDB collection for a user."""
    collection_name = f"user_{user_id.replace('@', '_').replace('.', '_')}"
    return _chroma_client.get_or_create_collection(name=collection_name)


async def ingest_file(user_id: str, filename: str, content: bytes) -> int:
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
        text = await loop.run_in_executor(None, _extract_pdf_text, content)
    elif ext == "txt":
        text = content.decode("utf-8", errors="replace")
    else:
        raise ValueError(f"Unsupported file type: .{ext}")

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
    collection = _get_collection(user_id)

    for i, chunk in enumerate(chunks):
        chunk_id = f"{filename}__chunk_{i}"
        embedding = await loop.run_in_executor(None, get_embedding, chunk)
        collection.upsert(
            ids=[chunk_id],
            documents=[chunk],
            embeddings=[embedding.tolist()],
            metadatas=[{"filename": filename, "chunk_index": i}],
        )

    logger.info("Ingested %d chunks from %s for user %s", len(chunks), filename, user_id)
    return len(chunks)


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
        collection = _get_collection(user_id)

        # Check if collection has any documents
        if collection.count() == 0:
            return []

        query_embedding = await loop.run_in_executor(None, get_embedding, query)

        results = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=min(n_results, collection.count()),
        )

        documents = results.get("documents", [[]])[0]
        return documents

    except Exception as exc:
        logger.error("RAG retrieval error: %s", exc)
        return []


async def clear_user_docs(user_id: str) -> None:
    """Delete all documents for a user from the vector store."""
    try:
        collection_name = f"user_{user_id.replace('@', '_').replace('.', '_')}"
        _chroma_client.delete_collection(name=collection_name)
        logger.info("Cleared documents for user %s", user_id)
    except Exception as exc:
        logger.warning("Error clearing docs for %s: %s", user_id, exc)
