
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel

from app.auth import get_current_user
from app.services.rag_pipeline import ingest_file, retrieve_docs, clear_user_docs
from app.services.llm_agent import query_llm
from app.services.audio import process_browser_audio
from app.services.chat_memory import add_message, get_recent_history
from app.validators import validate_file_type, validate_file_size
from app.config import get_settings
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/docs", tags=["Documents"])

MAX_FILE_SIZE_MB = 50
ALLOWED_FILE_TYPES = ["pdf", "txt"]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class DocsChatRequest(BaseModel):
    """Chat request for the docs page."""
    query: str
    voice_audio: str | None = None  # optional base64 PCM for voice input
    use_rag: bool = True  # True = RAG mode, False = plain LLM


class DocsChatResponse(BaseModel):
    """Chat response."""
    response: str
    sources_used: bool  # whether RAG context was included


class UploadResponse(BaseModel):
    """Document upload response."""
    filename: str
    status: str
    chunks_ingested: int


class ClearDocsResponse(BaseModel):
    """Clear documents response."""
    status: str


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
) -> UploadResponse:
    """
    Upload and ingest a document for RAG retrieval.

    Supports PDF and TXT files up to 50 MB.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    validate_file_type(file.filename, ALLOWED_FILE_TYPES)

    content = await file.read()
    validate_file_size(len(content), MAX_FILE_SIZE_MB)

    try:
        num_chunks = await ingest_file(user_id, file.filename, content)
        logger.info(
            "Document uploaded: %s by %s (%d chunks)",
            file.filename,
            user_id,
            num_chunks,
        )
        return UploadResponse(
            filename=file.filename,
            status="ingested",
            chunks_ingested=num_chunks,
        )
    except Exception as exc:
        logger.error("Document ingestion error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process document",
        )


@router.delete("/clear", response_model=ClearDocsResponse)
async def clear_documents(
    user_id: str = Depends(get_current_user),
) -> ClearDocsResponse:
    """Clear all uploaded documents for the current user."""
    try:
        await clear_user_docs(user_id)
        logger.info("Documents cleared for user: %s", user_id)
        return ClearDocsResponse(status="cleared")
    except Exception as exc:
        logger.error("Error clearing docs: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear documents",
        )


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


@router.post("/chat", response_model=DocsChatResponse)
async def docs_chat(
    request: DocsChatRequest,
    user_id: str = Depends(get_current_user),
) -> DocsChatResponse:
    """
    Dual-mode chat endpoint for the docs page.

    - RAG mode (default): retrieves relevant document chunks and includes
      them as context in the LLM prompt.
    - Plain LLM mode: bypasses RAG, directly queries the LLM.

    Optionally accepts voice input as base64 PCM audio.
    """
    query = request.query

    # Transcribe voice input if provided
    if request.voice_audio and not query.strip():
        from app.services.deepgram import get_file_transcriber

        transcriber = get_file_transcriber()
        pcm_bytes = process_browser_audio(request.voice_audio)
        if pcm_bytes:
            query = await transcriber.transcribe(pcm_bytes)
        if not query:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not transcribe voice input",
            )

    if not query or not query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query cannot be empty",
        )

    sources_used = False

    # Retrieve RAG context if enabled
    rag_context = ""
    if request.use_rag:
        try:
            docs = await retrieve_docs(user_id, query)
            if docs:
                rag_context = "\n\n".join(docs)
                sources_used = True
        except Exception as exc:
            logger.warning("RAG retrieval failed: %s", exc)

    # Build prompt
    history = await get_recent_history(user_id, limit=3)
    history_text = ""
    for msg in history:
        role_label = "User" if msg["role"] == "user" else "Assistant"
        history_text += f"{role_label}: {msg['content']}\n"

    if sources_used and rag_context:
        prompt = (
            "You are a knowledgeable AI assistant. Answer the user's question "
            "based on the following document context and conversation history.\n\n"
            f"Document Context:\n{rag_context}\n\n"
            f"Conversation History:\n{history_text}\n\n"
            f"User: {query}\n\nAssistant:"
        )
    else:
        prompt = (
            "You are a helpful AI assistant. Answer the user's question "
            "based on the conversation history.\n\n"
            f"Conversation History:\n{history_text}\n\n"
            f"User: {query}\n\nAssistant:"
        )

    try:
        response = await query_llm(prompt)

        # Persist to chat memory
        await add_message(user_id, "user", query)
        await add_message(user_id, "assistant", response)

        return DocsChatResponse(response=response, sources_used=sources_used)

    except Exception as exc:
        logger.error("Docs chat error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate response",
        )
