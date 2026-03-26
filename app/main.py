from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Starlette 1.x removed `on_startup/on_shutdown` kwargs; FastAPI still passes them
# in older compatibility paths. Patch Router.__init__ to ignore these extras so we
# can run with the bundled Starlette version when dependency pinning is unavailable.
try:  # pragma: no cover - defensive compatibility shim
    import starlette.routing as _sr

    _orig_router_init = _sr.Router.__init__

    def _patched_router_init(self, *args, **kwargs):
        kwargs.pop("on_startup", None)
        kwargs.pop("on_shutdown", None)
        result = _orig_router_init(self, *args, **kwargs)
        # Starlette 1.x no longer sets these attributes; FastAPI still expects them.
        if not hasattr(self, "on_startup"):
            self.on_startup = []
        if not hasattr(self, "on_shutdown"):
            self.on_shutdown = []
        return result

    _sr.Router.__init__ = _patched_router_init
except Exception:
    pass

from app.services.chat_memory import init_db
from app.config import get_settings
from app.logger import get_logger
from app.utils.embedding_utils import preload_embedding_model

logger = get_logger(__name__)
settings = get_settings()
settings.validate_security()


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("Starting Kontext Agent")
    await init_db()
    logger.info("Database initialized")
    try:
        preload_embedding_model()
    except Exception as exc:
        logger.warning("Embedding model preload failed (will lazy-load later): %s", exc)
    yield
    logger.info("Shutting down Kontext Agent")


app = FastAPI(
    title="Kontext Agent",
    version="1.0.0",
    description=(
        "AI-powered voice and document assistant with real-time transcription, "
        "meeting summarization, and RAG-based document chat."
    ),
    lifespan=lifespan,
)



app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



from app.routes.auth import router as auth_router
from app.routes.chat import router as chat_router
from app.routes.docs import router as docs_router
from app.routes.meeting import router as meeting_router
from app.routes.voice_chat import router as voice_chat_router

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(docs_router)
app.include_router(meeting_router)
app.include_router(voice_chat_router)




@app.get("/")
async def root():
    """API health check endpoint."""
    return {
        "name": "Kontext Agent",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
