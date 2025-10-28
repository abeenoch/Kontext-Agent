from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
import os
import asyncio

from app.services.meeting_agent import start_recording, stop_recording, transcribe_meeting, summarize_meeting, email_summary_brevo

router = APIRouter(prefix="/meeting", tags=["Meeting"])


class StartResponse(BaseModel):
    file_path: str


class StopResponse(BaseModel):
    file_path: str


class SummarizeRequest(BaseModel):
    user_id: str
    audio_path: str
    send_email: bool = False
    email_recipients: list[str] | None = None
    subject: str | None = None


@router.post("/start", response_model=StartResponse)
async def start(user_id: str):
    """Start recording for a user. Returns the file path that will be written to."""
    try:
        path = start_recording(user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"file_path": path}


@router.post("/stop", response_model=StopResponse)
async def stop(user_id: str):
    """Stop recording and return saved file path."""
    path = stop_recording(user_id)
    if not path:
        raise HTTPException(status_code=404, detail="No active recording for user")
    return {"file_path": path}


@router.post("/summarize")
async def summarize(req: SummarizeRequest, background_tasks: BackgroundTasks):
    """
    Transcribe and summarize an audio file, optionally send email.
    - user_id: owner of the recording (used for RAG context)
    - audio_path: local path to the saved wav
    """
    if not os.path.exists(req.audio_path):
        raise HTTPException(status_code=404, detail="audio_path not found")

    # 1) Transcribe (runs in thread)
    transcript = await transcribe_meeting(req.audio_path)

    # 2) Summarize (uses LLM and RAG)
    summary_result = await summarize_meeting(req.user_id, transcript, include_documents=True)

    # 3) Optionally email in the background
    if req.send_email and req.email_recipients:
        html = f"<h3>Meeting summary</h3><p>{summary_result.get('summary')}</p><h4>Action items</h4><p>{summary_result.get('action_items')}</p>"
        subject = req.subject or "Meeting summary"
        # run email in background to avoid blocking
        background_tasks.add_task(email_summary_brevo, subject, html, req.email_recipients)

    return {"transcript": transcript, "summary": summary_result}
