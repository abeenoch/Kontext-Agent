import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.database import db
from app.models.schemas import (
    MeetingInfo, MeetingStatus, MeetingStatusResponse,
    TranscriptSegment, SummarySegment, SummaryData, ChatMessage
)
from app.core.summarizer import summarizer
from app.core.rag_engine import rag_engine
from app.services.email_service import email_service
from app.services.notion_service import notion_service
from app.config import settings

logger = logging.getLogger(__name__)


class MeetingService:
    """Service for meeting operations."""
    
    async def create_meeting(self, title: str, participants: List[str]) -> str:
        """Create a new meeting."""
        meeting_id = f"meeting-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        await db.create_meeting(meeting_id, title, participants)
        logger.info(f"Created meeting {meeting_id}: {title}")
        return meeting_id
    
    async def get_meeting_status(self, meeting_id: str) -> Optional[MeetingStatusResponse]:
        """
        Get complete meeting status for polling.
        Returns structured response that Streamlit UI expects.
        """
        # Get meeting info
        meeting_data = await db.get_meeting(meeting_id)
        if not meeting_data:
            logger.warning(f"Meeting {meeting_id} not found")
            return None
        
        # Parse meeting info with safe defaults
        try:
            meeting_info = MeetingInfo(
                meeting_id=meeting_data["meeting_id"],
                title=meeting_data.get("title", "Untitled Meeting"),
                participants=meeting_data.get("participants", []),
                status=MeetingStatus(meeting_data.get("status", "recording")),
                started_at=self._parse_datetime(meeting_data.get("started_at")),
                ended_at=self._parse_datetime(meeting_data.get("ended_at")) if meeting_data.get("ended_at") else None
            )
        except Exception as e:
            logger.error(f"Error parsing meeting info: {e}", exc_info=True)
            return None
        
        # Get transcript segments
        try:
            transcript_segments = await db.get_all_transcripts(meeting_id)
            transcripts = []
            for t in transcript_segments:
                try:
                    transcripts.append(TranscriptSegment(
                        id=t.get("id", 0),
                        meeting_id=t["meeting_id"],
                        text=t.get("text", ""),
                        timestamp=self._parse_datetime(t.get("timestamp")),
                        speaker=t.get("speaker")
                    ))
                except Exception as e:
                    logger.warning(f"Error parsing transcript segment: {e}")
                    continue
        except Exception as e:
            logger.error(f"Error fetching transcripts: {e}", exc_info=True)
            transcripts = []
        
        # Get latest 5 transcripts for display
        latest_transcripts = transcripts[-5:] if len(transcripts) > 5 else transcripts
        
        # Get summaries
        try:
            summary_segments = await db.get_all_summaries(meeting_id)
            summaries = []
            for s in summary_segments:
                try:
                    # Handle summary data structure
                    summary_dict = s.get("summary", {})
                    if isinstance(summary_dict, str):
                        import json
                        summary_dict = json.loads(summary_dict)
                    
                    summaries.append(SummarySegment(
                        id=s.get("id", 0),
                        meeting_id=s["meeting_id"],
                        summary=SummaryData(**summary_dict) if summary_dict else SummaryData(),
                        is_final=bool(s.get("is_final", False)),
                        timestamp=self._parse_datetime(s.get("timestamp"))
                    ))
                except Exception as e:
                    logger.warning(f"Error parsing summary segment: {e}")
                    continue
        except Exception as e:
            logger.error(f"Error fetching summaries: {e}", exc_info=True)
            summaries = []
        
        # Get latest summary
        latest_summary = summaries[-1] if summaries else None
        
        # Get final summary if meeting is completed
        final_summary = None
        if meeting_info.status == MeetingStatus.COMPLETED:
            try:
                final_summaries = [s for s in summaries if s.is_final]
                if final_summaries:
                    final_summary = final_summaries[-1].summary
                else:
                    # Try to get from DB directly
                    final_summary_data = await db.get_final_summary(meeting_id)
                    if final_summary_data:
                        if isinstance(final_summary_data, dict):
                            final_summary = SummaryData(**final_summary_data)
                        else:
                            import json
                            final_summary = SummaryData(**json.loads(final_summary_data))
            except Exception as e:
                logger.warning(f"Error fetching final summary: {e}", exc_info=True)
        
        # Get chat messages
        try:
            chat_data = await db.get_chat_history(meeting_id)
            chat_messages = []
            for c in chat_data:
                try:
                    chat_messages.append(ChatMessage(
                        id=c.get("id", 0),
                        meeting_id=c["meeting_id"],
                        role=c.get("role", "user"),
                        content=c.get("content", ""),
                        timestamp=self._parse_datetime(c.get("timestamp"))
                    ))
                except Exception as e:
                    logger.warning(f"Error parsing chat message: {e}")
                    continue
        except Exception as e:
            logger.error(f"Error fetching chat history: {e}", exc_info=True)
            chat_messages = []
        
        # Build response
        return MeetingStatusResponse(
            meeting=meeting_info,
            transcript_count=len(transcripts),
            latest_transcripts=latest_transcripts,
            summaries_count=len(summaries),
            latest_summary=latest_summary,
            final_summary=final_summary,
            chat_messages=chat_messages,
            is_recording=(meeting_info.status == MeetingStatus.RECORDING)
        )
    
    def _parse_datetime(self, dt_string: Any) -> datetime:
        """Safely parse datetime string."""
        if isinstance(dt_string, datetime):
            return dt_string
        if isinstance(dt_string, str):
            try:
                return datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
            except:
                pass
        # Default to now if parsing fails
        return datetime.utcnow()
    
    async def get_full_transcript(self, meeting_id: str) -> str:
        """Get complete meeting transcript as text."""
        try:
            return await db.get_full_transcript(meeting_id)
        except Exception as e:
            logger.error(f"Error getting full transcript: {e}", exc_info=True)
            return ""
    
    async def send_chat_message(self, meeting_id: str, message: str) -> str:
        """Handle chat message and return AI response."""
        # Validate meeting exists
        meeting = await db.get_meeting(meeting_id)
        if not meeting:
            raise ValueError(f"Meeting {meeting_id} not found")
        
        # Save user message
        await db.add_chat_message(meeting_id, "user", message)
        
        # Get context from RAG (with fallback)
        try:
            context = await rag_engine.query_meeting_context(meeting_id, message)
            if not context:
                logger.info("RAG returned no context, falling back to full transcript")
                context = await db.get_full_transcript(meeting_id)
        except Exception as e:
            logger.warning(f"RAG query failed: {e}, using transcript")
            context = await db.get_full_transcript(meeting_id)
        
        # Generate response
        try:
            response = await summarizer.answer_question(message, context)
        except Exception as e:
            logger.error(f"Error generating answer: {e}", exc_info=True)
            response = "I apologize, but I encountered an error processing your question. Please try again."
        
        # Save assistant message
        await db.add_chat_message(meeting_id, "assistant", response)
        
        logger.info(f"Chat message processed for meeting {meeting_id}")
        return response
    
    async def _get_or_generate_final_summary(self, meeting_id: str) -> Dict[str, Any]:
        """
        Get final summary from DB or generate if not exists.
        Returns dict format suitable for email/notion.
        """
        # Try to get existing final summary
        try:
            final_summary = await db.get_final_summary(meeting_id)
            if final_summary:
                if isinstance(final_summary, str):
                    import json
                    return json.loads(final_summary)
                return final_summary
        except Exception as e:
            logger.warning(f"Error fetching final summary: {e}")
        
        # Generate new final summary
        transcript = await db.get_full_transcript(meeting_id)
        if not transcript or len(transcript) < 20:
            raise ValueError("Transcript is too short to generate summary")
        
        summary = await summarizer.summarize_final(transcript)
        
        # Store it
        await db.add_summary(meeting_id, summary, is_final=True)
        
        return summary
    
    async def send_summary_email(self, meeting_id: str, recipients: List[str]) -> bool:
        """Send meeting summary via email."""
        if not recipients:
            raise ValueError("Recipients list cannot be empty")
        
        # Get meeting data
        meeting_data = await db.get_meeting(meeting_id)
        if not meeting_data:
            raise ValueError(f"Meeting {meeting_id} not found")
        
        # Get or generate final summary
        try:
            summary = await self._get_or_generate_final_summary(meeting_id)
        except Exception as e:
            logger.error(f"Failed to get/generate summary: {e}", exc_info=True)
            raise ValueError(f"Could not generate summary: {e}")
        
        # Send email
        try:
            # email_service expects: (meeting_id, summary, recipients)
            # But might need title too - check your email_service.py
            success = await email_service.send_summary(
                meeting_id=meeting_id,
                title=meeting_data.get("title", "Meeting Summary"),
                summary=summary,
                recipients=recipients
            )
            
            # Log integration
            if success:
                await db.log_integration(
                    meeting_id, 
                    "email", 
                    "success", 
                    {"recipients": recipients}
                )
            else:
                await db.log_integration(meeting_id, "email", "failed")
            
            return success
        except Exception as e:
            logger.error(f"Email sending failed: {e}", exc_info=True)
            await db.log_integration(
                meeting_id, 
                "email", 
                "failed", 
                {"error": str(e), "recipients": recipients}
            )
            return False
    
    async def push_to_notion(self, meeting_id: str) -> Optional[str]:
        """Push meeting summary to Notion."""
        # Check if Notion is configured
        if not settings.NOTION_API_KEY or not settings.NOTION_DATABASE_ID:
            raise ValueError("Notion integration not configured")
        
        # Get meeting data
        meeting_data = await db.get_meeting(meeting_id)
        if not meeting_data:
            raise ValueError(f"Meeting {meeting_id} not found")
        
        # Get or generate final summary
        try:
            summary = await self._get_or_generate_final_summary(meeting_id)
        except Exception as e:
            logger.error(f"Failed to get/generate summary: {e}", exc_info=True)
            raise ValueError(f"Could not generate summary: {e}")
        
        # Push to Notion
        try:
            # notion_service expects: (meeting_id, summary, title=...)
            page_url = await notion_service.push_summary(
                meeting_id=meeting_id,
                summary=summary,
                title=meeting_data.get("title", "Meeting Summary")
            )
            
            # Log integration
            if page_url:
                await db.log_integration(
                    meeting_id,
                    "notion",
                    "success",
                    {"url": page_url}
                )
            else:
                await db.log_integration(meeting_id, "notion", "failed")
            
            return page_url
        except Exception as e:
            logger.error(f"Notion push failed: {e}", exc_info=True)
            await db.log_integration(
                meeting_id,
                "notion",
                "failed",
                {"error": str(e)}
            )
            return None
    
    async def stop_meeting(self, meeting_id: str):
        """Mark meeting as completed (called by WebSocket handler)."""
        await db.update_meeting_status(meeting_id, "completed", datetime.utcnow())
        logger.info(f"Meeting {meeting_id} marked as completed")
    
    async def list_meetings(self, limit: int = 20) -> List[MeetingInfo]:
        """List recent meetings."""
        try:
            meetings_data = await db.list_meetings(limit)
            
            result = []
            for m in meetings_data:
                try:
                    result.append(MeetingInfo(
                        meeting_id=m["meeting_id"],
                        title=m.get("title", "Untitled"),
                        participants=m.get("participants", []),
                        status=MeetingStatus(m.get("status", "recording")),
                        started_at=self._parse_datetime(m.get("started_at")),
                        ended_at=self._parse_datetime(m.get("ended_at")) if m.get("ended_at") else None
                    ))
                except Exception as e:
                    logger.warning(f"Error parsing meeting: {e}")
                    continue
            
            return result
        except Exception as e:
            logger.error(f"Error listing meetings: {e}", exc_info=True)
            return []


meeting_service = MeetingService()