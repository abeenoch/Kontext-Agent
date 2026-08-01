
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
    BackgroundTasks,
    Form,
    Query,
)
from pydantic import BaseModel

from app.auth import get_current_user
from app.services.rag_pipeline import retrieve_docs, clear_user_docs, ingest_file
from app.services.llm_agent import query_llm
from app.services.audio import process_browser_audio
from app.services.chat_memory import add_message, get_recent_history
from app.services.doc_jobs import process_doc_job, get_job
from app.services.chat_memory import create_doc_job, update_doc_job
from app.utils.redaction import redact_pii
from app.prompts import (
    DOCS_SYSTEM_PROMPT,
    DOCS_NO_RAG_SYSTEM_PROMPT,
    build_docs_user,
    build_docs_no_rag_user,
)
from app.validators import validate_file_type, validate_file_size
from app.config import get_settings
from app.logger import get_logger
import httpx

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/docs", tags=["Documents"])

MAX_FILE_SIZE_MB = 300
ALLOWED_FILE_TYPES = ["pdf", "txt"]




class DocsChatRequest(BaseModel):
    """Chat request for the docs page."""
    query: str
    voice_audio: str | None = None  
    use_rag: bool = True  # True = RAG mode
    job_id: str | None = None  #  wait for specific ingestion job completion


class DocsChatResponse(BaseModel):
    """Chat response."""
    response: str
    sources_used: bool  # whether RAG context was included


class UploadResponse(BaseModel):
    """Document upload response."""
    filename: str
    status: str
    job_id: str
    chunks_ingested: int | None = None


class JobStatusResponse(BaseModel):
    """Job status response."""
    id: str
    filename: str
    status: str
    chunks_ingested: int | None = None
    error: str | None = None


class ClearDocsResponse(BaseModel):
    """Clear documents response."""
    status: str


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    user_id: str = Depends(get_current_user),
    tab_id: str = Query("default", description="Tab id for this job"),
) -> JobStatusResponse:
    job = await get_job(job_id, user_id, tab_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobStatusResponse(
        id=job["id"],
        filename=job["filename"],
        status=job["status"],
        chunks_ingested=job.get("chunks_ingested"),
        error=job.get("error"),
    )



@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    tab_id: str = Form("default", description="Tab id for this upload"),
    background_tasks: BackgroundTasks = None,
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
        job_id = await create_doc_job(user_id, file.filename, tab_id)

        # In test/development, process inline to keep behavior predictable and fast.
        if settings.app_env in {"test", "development"} or background_tasks is None:
            try:
                chunks = await ingest_file(user_id, tab_id, file.filename, content)
            except TypeError:
                # Backward compatibility for test stubs without tab_id arg
                chunks = await ingest_file(user_id, file.filename, content)  # type: ignore[misc]
            await update_doc_job(
                job_id, status="completed", chunks_ingested=chunks, error=None
            )
            return UploadResponse(
                filename=file.filename,
                status="ingested",
                job_id=job_id,
                chunks_ingested=chunks,
            )

        # Production path: process asynchronously to avoid blocking the request.
        background_tasks.add_task(
            process_doc_job, job_id, user_id, tab_id, file.filename, content
        )
        logger.info(
            "Doc upload queued: %s by %s (job=%s, tab=%s)",
            file.filename,
            user_id,
            job_id,
            tab_id,
        )
        return UploadResponse(
            filename=file.filename,
            status="queued",
            job_id=job_id,
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
    tab_id: str = Query("default", description="Tab id to clear"),
) -> ClearDocsResponse:
    """Clear all uploaded documents for the current user."""
    try:
        await clear_user_docs(user_id, tab_id)
        logger.info("Documents cleared for user: %s tab %s", user_id, tab_id)
        return ClearDocsResponse(status="cleared")
    except Exception as exc:
        logger.error("Error clearing docs: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear documents",
        )


@router.post("/chat", response_model=DocsChatResponse)
async def docs_chat(
    request: DocsChatRequest,
    user_id: str = Depends(get_current_user),
    tab_id: str = Query("default", description="Tab id for RAG retrieval"),
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

    # If a specific job was provided, ensure it's complete before chatting.
    if request.job_id:
        job = await get_job(request.job_id, user_id, tab_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ingestion job not found",
            )
        if job["status"] != "completed":
            raise HTTPException(
                status_code=status.HTTP_425_TOO_EARLY,
                detail=f"Job status: {job['status']}",
            )

    sources_used = False

    # Retrieve RAG context if enabled
    rag_context = ""
    if request.use_rag:
        try:
            docs = await retrieve_docs(user_id, tab_id, query)
            if docs:
                rag_context = redact_pii("\n\n".join(docs))
                sources_used = True
        except TypeError:
            docs = await retrieve_docs(user_id, query)  # type: ignore[arg-type]
            if docs:
                rag_context = redact_pii("\n\n".join(docs))
                sources_used = True
        except Exception as exc:
            logger.warning("RAG retrieval failed: %s", exc)

    # Build prompt
    history_limit = 0 if sources_used else 3
    history = await get_recent_history(user_id, limit=history_limit, tab_id=tab_id) if history_limit > 0 else []
    history_text = ""
    for msg in history:
        role_label = "User" if msg["role"] == "user" else "Assistant"
        history_text += f"{role_label}: {msg['content']}\n"

    if sources_used and rag_context:
        system_prompt = DOCS_SYSTEM_PROMPT
        user_prompt = build_docs_user(rag_context, history_text, query)
    else:
        system_prompt = DOCS_NO_RAG_SYSTEM_PROMPT
        user_prompt = build_docs_no_rag_user(history_text, query)

    try:
        response = await query_llm(user_prompt, system_prompt=system_prompt)

        # Persist to chat memory
        await add_message(user_id, "user", query, tab_id=tab_id)
        await add_message(user_id, "assistant", response, tab_id=tab_id)

        return DocsChatResponse(response=response, sources_used=sources_used)

    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 503:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="LLM provider temporarily unavailable. Please retry shortly.",
            )
        logger.error("Docs chat HTTP error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream LLM error",
        )
    except Exception as exc:
        logger.error("Docs chat error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate response",
        )
