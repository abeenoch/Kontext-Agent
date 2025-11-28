from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class MeetingStatus(str, Enum):
    """Meeting status enum."""
    RECORDING = "recording"
    COMPLETED = "completed"
    FAILED = "failed"



class StartMeetingRequest(BaseModel):
    """Request to start a new meeting."""
    title: str = Field(..., min_length=1, max_length=200)
    participants: List[str] = Field(default_factory=list)


class ChatMessageRequest(BaseModel):
    """Request to send a chat message."""
    message: str = Field(..., min_length=1, max_length=2000)


class SendEmailRequest(BaseModel):
    """Request to send meeting summary via email."""
    recipients: List[str] = Field(..., min_items=1)



class TranscriptSegment(BaseModel):
    """A single transcript segment."""
    id: int
    meeting_id: str
    text: str
    timestamp: datetime
    speaker: Optional[str] = None


class SummaryData(BaseModel):
    """Summary data structure."""
    overview: Optional[str] = None
    key_points: List[str] = Field(default_factory=list)
    decisions: List[str] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)
    participants_summary: Optional[Dict[str, Any]] = None


class SummarySegment(BaseModel):
    """A summary segment (periodic or final)."""
    id: int
    meeting_id: str
    summary: SummaryData
    is_final: bool
    timestamp: datetime


class ChatMessage(BaseModel):
    """A chat message."""
    id: int
    meeting_id: str
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime


class MeetingInfo(BaseModel):
    """Basic meeting information."""
    meeting_id: str
    title: str
    participants: List[str]
    status: MeetingStatus
    started_at: datetime
    ended_at: Optional[datetime] = None


class MeetingStatusResponse(BaseModel):
    """Complete meeting status for polling."""
    meeting: MeetingInfo
    transcript_count: int
    latest_transcripts: List[TranscriptSegment]
    summaries_count: int
    latest_summary: Optional[SummarySegment] = None
    final_summary: Optional[SummaryData] = None
    chat_messages: List[ChatMessage]
    is_recording: bool


class MeetingCreatedResponse(BaseModel):
    """Response when meeting is created."""
    meeting_id: str
    status: str
    message: str


class EmailSentResponse(BaseModel):
    """Response after sending email."""
    success: bool
    recipients: List[str]
    message: str


class NotionPushResponse(BaseModel):
    """Response after pushing to Notion."""
    success: bool
    page_url: Optional[str] = None
    message: str


class ErrorResponse(BaseModel):
    """Error response."""
    error: str
    detail: Optional[str] = None



class WSStartMessage(BaseModel):
    """WebSocket START message."""
    type: str = "START"
    metadata: Dict[str, Any]


class WSAudioChunk(BaseModel):
    """WebSocket AUDIO_CHUNK message."""
    type: str = "AUDIO_CHUNK"
    meeting_id: str
    data: str  # base64 encoded audio
    chunk_index: int
    timestamp: float


class WSStopMessage(BaseModel):
    """WebSocket STOP message."""
    type: str = "STOP"
    meeting_id: str


class WSChatMessage(BaseModel):
    """WebSocket CHAT message."""
    type: str = "CHAT"
    meeting_id: str
    message: str


class WSPingMessage(BaseModel):
    """WebSocket PING message."""
    type: str = "PING"
    meeting_id: str