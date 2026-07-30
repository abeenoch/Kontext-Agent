import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    app_env: str = os.getenv("APP_ENV", "development").lower()

    database_url: str = os.getenv("DATABASE_URL", "")
    chroma_dir: str = os.getenv("CHROMA_DIR", "./chroma_db")

    #transcripts_dir: str = os.getenv("TRANSCRIPTS_DIR", "data/meeting_transcripts")
    encryption_key: str = os.getenv("ENCRYPTION_KEY", "")  # used for AES-GCM of transcripts/summaries
    meeting_retention_days: int = int(os.getenv("MEETING_RETENTION_DAYS", "90"))
    periodic_summary_lookback_minutes: int = int(
        os.getenv("PERIODIC_SUMMARY_LOOKBACK_MINUTES", "10")
    )

    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_url: str = "https://api.groq.com/openai/v1/chat/completions"
    groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    llm_provider: str = os.getenv("LLM_PROVIDER", "groq").lower()
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    llm_timeout: float = float(os.getenv("LLM_TIMEOUT", "30.0"))
    groq_input_cost_per_1k_tokens: float = float(
        os.getenv("GROQ_INPUT_COST_PER_1K_TOKENS", "0.0")
    )
    groq_output_cost_per_1k_tokens: float = float(
        os.getenv("GROQ_OUTPUT_COST_PER_1K_TOKENS", "0.0")
    )

    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    ollama_timeout: float = float(os.getenv("OLLAMA_TIMEOUT", "30.0"))
    ollama_keep_alive: str = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
    ollama_input_cost_per_1k_tokens: float = float(
        os.getenv("OLLAMA_INPUT_COST_PER_1K_TOKENS", "0.0")
    )
    ollama_output_cost_per_1k_tokens: float = float(
        os.getenv("OLLAMA_OUTPUT_COST_PER_1K_TOKENS", "0.0")
    )

    otel_service_name: str = os.getenv("OTEL_SERVICE_NAME", "kontext-agent")
    otel_exporter_otlp_endpoint: str = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    otel_exporter_otlp_headers: str = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
    otel_traces_enabled: bool = (
        os.getenv("OTEL_TRACES_ENABLED", "true").lower() == "true"
    )

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

    embedding_model: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    chunk_size: int = int(os.getenv("CHUNK_SIZE", "800"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "100"))

    websocket_timeout: float = float(os.getenv("WEBSOCKET_TIMEOUT", "900.0"))
    preload_embeddings: bool = os.getenv("PRELOAD_EMBEDDINGS", "true").lower() == "true"

    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_pass: str = os.getenv("SMTP_PASS", "")

    notion_token: str = os.getenv("NOTION_TOKEN", "")
    notion_page_id: str = os.getenv("NOTION_PAGE_ID", "")

    slack_bot_token: str = os.getenv("SLACK_BOT_TOKEN", "")
    slack_default_channel: str = os.getenv("SLACK_DEFAULT_CHANNEL", "#general")

    jwt_secret: str = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = int(os.getenv("JWT_EXPIRY_HOURS", "24"))
    cors_origins: str = os.getenv(
        "CORS_ORIGINS",
        "*",  # default open for local dev; tighten in production via env
    )
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

    rate_limit_requests: int = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
    rate_limit_period: int = int(os.getenv("RATE_LIMIT_PERIOD", "60"))

    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}

    def get_database_url(self) -> str:
        """
        Resolve the async SQLAlchemy database URL.

        For production, DATABASE_URL must be provided. In development/test, fall back to
        a local SQLite file (or CHAT_DB_PATH if supplied) so smoke tests and local runs
        do not require Postgres.
        """
        if self.database_url:
            return self.database_url.strip()

        if self.app_env in {"development", "test"}:
            chat_db_path = os.getenv("CHAT_DB_PATH", "data/dev.db").strip()
            # Allow passing a full sqlite URL or just a file path.
            if chat_db_path.startswith("sqlite"):
                return chat_db_path
            return f"sqlite+aiosqlite:///{chat_db_path}"

        raise RuntimeError(
            "DATABASE_URL is required (Postgres recommended). Example: "
            "'postgresql+asyncpg://user:pass@localhost:5432/kontext_agent'"
        )

    def get_cors_origins(self) -> list[str]:
        """Parse CORS origins from comma-separated env value."""
        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        # Allow wildcard for local/dev convenience
        if origins == ["*"]:
            return ["*"]
        return origins

    def get_encryption_key(self) -> str:
        """
        Return stable key material for AES-GCM.

        Prefers ENCRYPTION_KEY; falls back to JWT_SECRET to avoid breaking
        existing dev/test data while encouraging explicit configuration.
        """
        if self.encryption_key:
            return self.encryption_key
        return self.jwt_secret

    def validate_security(self) -> None:
        """
        Validate security-sensitive settings.

        In production, reject known-weak JWT secrets.
        """
        if self.app_env != "production":
            return

        weak_default = "your-secret-key-change-in-production"
        if self.jwt_secret == weak_default or len(self.jwt_secret) < 32:
            raise RuntimeError(
                "Unsafe JWT_SECRET for production. Set a strong random secret (>=32 chars)."
            )

        if "*" in self.get_cors_origins():
            raise RuntimeError(
                "Unsafe CORS_ORIGINS for production. Use explicit trusted origins."
            )


@lru_cache()
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
