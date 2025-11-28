import logging
from fastapi import APIRouter, HTTPException, status
from typing import List

from app.models.schemas import (
    StartMeetingRequest, MeetingCreatedResponse,
    MeetingStatusResponse, ChatMessageRequest,
    SendEmailRequest, EmailSentResponse,
    NotionPushResponse, ErrorResponse,
    MeetingInfo
)
from app.services.meeting_service import meeting_service
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["meetings"])



@router.post("/meetings", response_model=MeetingCreatedResponse)
async def create_meeting(request: StartMeetingRequest):
    """Create a new meeting (alternative to WebSocket START)."""
    try:
        meeting_id = await meeting_service.create_meeting(
            title=request.title,
            participants=request.participants
        )
        
        return MeetingCreatedResponse(
            meeting_id=meeting_id,
            status="created",
            message="Meeting created successfully"
        )
    except Exception as e:
        logger.error(f"Failed to create meeting: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/meetings/{meeting_id}/status", response_model=MeetingStatusResponse)
async def get_meeting_status(meeting_id: str):
    """
    Get complete meeting status - used for polling by frontend.
    
    This endpoint returns:
    - Meeting info (title, status, timestamps)
    - Latest transcript segments
    - Summaries (periodic and final)
    - Chat history
    - Recording status
    """
    try:
        status_data = await meeting_service.get_meeting_status(meeting_id)
        
        if not status_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Meeting {meeting_id} not found"
            )
        
        return status_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get meeting status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/meetings", response_model=List[MeetingInfo])
async def list_meetings(limit: int = 20):
    """List recent meetings."""
    try:
        return await meeting_service.list_meetings(limit)
    except Exception as e:
        logger.error(f"Failed to list meetings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/meetings/{meeting_id}/transcript", response_model=dict)
async def get_full_transcript(meeting_id: str):
    """Get complete meeting transcript."""
    try:
        transcript = await meeting_service.get_full_transcript(meeting_id)
        
        return {
            "meeting_id": meeting_id,
            "transcript": transcript
        }
    except Exception as e:
        logger.error(f"Failed to get transcript: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )




@router.post("/meetings/{meeting_id}/chat", response_model=dict)
async def send_chat_message(meeting_id: str, request: ChatMessageRequest):
    """Send a chat message and get AI response."""
    try:
        response = await meeting_service.send_chat_message(
            meeting_id=meeting_id,
            message=request.message
        )
        
        return {
            "meeting_id": meeting_id,
            "user_message": request.message,
            "assistant_response": response
        }
    except Exception as e:
        logger.error(f"Failed to process chat message: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )




@router.post("/meetings/{meeting_id}/send-email", response_model=EmailSentResponse)
async def send_summary_email(meeting_id: str, recipients: List[str]):
    """Send meeting summary via email."""
    try:
        if not recipients:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Recipients list cannot be empty"
            )
        
        success = await meeting_service.send_summary_email(
            meeting_id=meeting_id,
            recipients=recipients
        )
        
        if success:
            return EmailSentResponse(
                success=True,
                recipients=recipients,
                message=f"Summary sent to {len(recipients)} recipient(s)"
            )
        else:
            return EmailSentResponse(
                success=False,
                recipients=recipients,
                message="Failed to send email"
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to send email: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/meetings/{meeting_id}/push-notion", response_model=NotionPushResponse)
async def push_to_notion(meeting_id: str):
    """Push meeting summary to Notion."""
    try:
        if not settings.NOTION_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Notion integration not configured"
            )
        
        page_url = await meeting_service.push_to_notion(meeting_id)
        
        if page_url:
            return NotionPushResponse(
                success=True,
                page_url=page_url,
                message="Successfully pushed to Notion"
            )
        else:
            return NotionPushResponse(
                success=False,
                message="Failed to push to Notion"
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to push to Notion: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )




@router.get("/health", response_model=dict)
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "meeting-agent",
        "version": "1.0.0"
    }