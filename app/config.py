"""Application settings from environment variables."""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # -- Server -------------------------------------------------------------------
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8000"))

    # -- Database -----------------------------------------------------------------
    chat_db_path: str = os.getenv("CHAT_DB_PATH", "./chat_memory.db")
    chroma_dir: str = os.getenv("CHROMA_DIR", "./chroma_db")

    # -- File Storage -------------------------------------------------------------
    transcripts_dir: str = os.getenv("TRANSCRIPTS_DIR", "data/meeting_transcripts")

    # -- LLM (Groq) ---------------------------------------------------------------
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_url: str = "https://api.groq.com/openai/v1/chat/completions"
    groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    llm_timeout: float = float(os.getenv("LLM_TIMEOUT", "30.0"))

    # -- Deepgram -----------------------------------------------------------------
    deepgram_api_key: str = os.getenv("DEEPGRAM_API_KEY", "")
    deepgram_model: str = os.getenv("DEEPGRAM_MODEL", "nova-3")
    deepgram_language: str = os.getenv("DEEPGRAM_LANGUAGE", "en")
    deepgram_tts_model: str = os.getenv("DEEPGRAM_TTS_MODEL", "aura-2-thalia-en")
    deepgram_interim_results: bool = (
        os.getenv("DEEPGRAM_INTERIM_RESULTS", "true").lower() == "true"
    )
    deepgram_punctuate: bool = (
        os.getenv("DEEPGRAM_PUNCTUATE", "true").lower() == "true"
    )
    deepgram_diarize: bool = (
        os.getenv("DEEPGRAM_DIARIZE", "true").lower() == "true"
    )
    deepgram_smart_format: bool = (
        os.getenv("DEEPGRAM_SMART_FORMAT", "true").lower() == "true"
    )

    # -- Embeddings ---------------------------------------------------------------
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    # -- Text Processing ----------------------------------------------------------
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "800"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "100"))

    # -- WebSocket ----------------------------------------------------------------
    websocket_timeout: float = float(os.getenv("WEBSOCKET_TIMEOUT", "300.0"))

    # -- Email (SMTP) -------------------------------------------------------------
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_pass: str = os.getenv("SMTP_PASS", "")

    # -- Notion -------------------------------------------------------------------
    notion_token: str = os.getenv("NOTION_TOKEN", "")
    notion_page_id: str = os.getenv("NOTION_PAGE_ID", "")

    # -- Security -----------------------------------------------------------------
    jwt_secret: str = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = int(os.getenv("JWT_EXPIRY_HOURS", "24"))

    # -- Rate Limiting ------------------------------------------------------------
    rate_limit_requests: int = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
    rate_limit_period: int = int(os.getenv("RATE_LIMIT_PERIOD", "60"))

    # -- Logging ------------------------------------------------------------------
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
