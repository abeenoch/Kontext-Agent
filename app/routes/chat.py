from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth import get_current_user
from app.services.llm_agent import query_llm
from app.services.rag_pipeline import retrieve_docs
from app.services.chat_memory import add_message, get_recent_history, clear_history
from app.services.audio import process_browser_audio
from app.config import get_settings
from app.logger import get_logger
import httpx

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/chat", tags=["Chat"])


class ChatRequest(BaseModel):
    """Chat query request body."""
    query: str
    voice_audio: str | None = None  


class ChatResponse(BaseModel):
    """Chat query response body."""
    response: str
    sources_used: bool = False


class ClearResponse(BaseModel):
    """Chat history clear response."""
    status: str





@router.post("/query", response_model=ChatResponse)
async def chat_query(
    request: ChatRequest,
    user_id: str = Depends(get_current_user),
) -> ChatResponse:
    """
    Query the AI assistant with text or voice input.

    Automatically includes RAG context if the user has uploaded documents.
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

    # Retrieve RAG context
    sources_used = False
    rag_context = ""
    try:
        docs = await retrieve_docs(user_id, query)
        if docs:
            rag_context = "\n\n".join(docs)
            sources_used = True
    except Exception as exc:
        logger.warning("RAG retrieval error: %s", exc)

    # Get conversation history
    history = await get_recent_history(user_id, limit=5)
    history_text = ""
    for msg in history:
        role_label = "User" if msg["role"] == "user" else "Assistant"
        history_text += f"{role_label}: {msg['content']}\n"

    # Build prompt
    if sources_used:
        prompt = (
            "You are a helpful AI assistant. Answer the user's question "
            "using the following context and conversation history.\n\n"
            f"Context:\n{rag_context}\n\n"
            f"History:\n{history_text}\n\n"
            f"User: {query}\n\nAssistant:"
        )
    else:
        prompt = (
            "You are a helpful AI assistant.\n\n"
            f"History:\n{history_text}\n\n"
            f"User: {query}\n\nAssistant:"
        )

    try:
        response = await query_llm(prompt)

        await add_message(user_id, "user", query)
        await add_message(user_id, "assistant", response)

        return ChatResponse(response=response, sources_used=sources_used)

    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        logger.error("Chat query http error: %s", exc)
        if status_code == 503:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="LLM provider is temporarily unavailable. Please retry in a moment.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream LLM error",
        )
    except Exception as exc:
        logger.error("Chat query error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate response",
        )


@router.delete("/history", response_model=ClearResponse)
async def clear_chat_history(
    user_id: str = Depends(get_current_user),
) -> ClearResponse:
    """Clear the chat history for the current user."""
    await clear_history(user_id)
    return ClearResponse(status="cleared")
