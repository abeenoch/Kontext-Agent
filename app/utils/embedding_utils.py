from app.config import get_settings
from app.logger import get_logger

_model = None
_model_name = None
_logger = get_logger(__name__)


def _ensure_model_loaded():
    """Load the embedding model once"""
    global _model, _model_name
    if _model is not None:
        return

    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    _model_name = settings.embedding_model or "all-MiniLM-L6-v2"
    _logger.info("Loading embedding model: %s", _model_name)
    _model = SentenceTransformer(_model_name)
    _logger.info("Embedding model loaded: %s", _model_name)


def preload_embedding_model() -> None:
    """
    Explicitly load the embedding model at startup so later requests
    don't block on download/initialization.
    """
    _ensure_model_loaded()


def get_embedding(text: str):
    """Get embedding for text, lazy-loading model on first use."""
    _ensure_model_loaded()
    return _model.encode([text])[0]
