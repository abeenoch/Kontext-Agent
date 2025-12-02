from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    ALLOWED_ORIGINS: str = "http://localhost:8501,http://localhost:3000"
    
    # Database
    DB_PATH: str = "./data/meetings.db"
    
    # Whisper
    WHISPER_MODEL: str = "base"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    
    # LLM (Optional - summarization will gracefully degrade without it)
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.1-70b-preview"
    
    # Pinecone (Optional - RAG indexing will gracefully fail without it)
    PINECONE_API_KEY: Optional[str] = None
    PINECONE_ENVIRONMENT: str = "us-east-1-aws"
    PINECONE_INDEX_NAME: str = "meeting-agent"
    
    # Email (Optional - email functionality will gracefully fail without it)
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None
    SMTP_USE_TLS: bool = True
    
    # Notion (Optional)
    NOTION_API_KEY: Optional[str] = None
    NOTION_DATABASE_ID: Optional[str] = None
    
    # Audio Processing
    SAMPLE_RATE: int = 16000
    AUDIO_CHANNELS: int = 1
    CHUNK_DURATION_MS: int = 500
    TRANSCRIPTION_WINDOW_SEC: int = 60 
    SUMMARY_INTERVAL_MIN: int = 10
    MIN_AUDIO_DURATION_SEC: int = 10
    
    # Streaming Mode
    ENABLE_STREAMING: bool = True  # Use Groq streaming API for real-time transcription
    STREAMING_PARTIAL_UPDATE_INTERVAL_MS: int = 100  # Update UI every 100-300ms with partial results
    FRAME_SIZE_MS: int = 20  # Send 20ms audio frames for streaming (was 500ms chunks)
    STREAMING_SUMMARY_INTERVAL_MIN: int = 0  # Summary interval in streaming mode (0 = every 30s, overrides SUMMARY_INTERVAL_MIN)
    
    # FFmpeg (optional)
    FFMPEG_PATH: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse comma-separated origins."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]
    
    @property
    def summary_interval_seconds(self) -> int:
        """Convert summary interval to seconds."""
        return self.SUMMARY_INTERVAL_MIN * 60
    
    @property
    def chunk_size_bytes(self) -> int:
        """Calculate audio chunk size in bytes (PCM S16LE)."""
        return self.SAMPLE_RATE * self.AUDIO_CHANNELS * 2 * self.CHUNK_DURATION_MS // 1000


settings = Settings()