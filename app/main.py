"""
Kontext Agent -- main application entry point.

AI-powered voice and document assistant with real-time transcription,
meeting summarization, and RAG-based document chat.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.services.chat_memory import init_db
from app.config import get_settings
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("Starting Kontext Agent v4.0.0")
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down Kontext Agent")


app = FastAPI(
    title="Kontext Agent",
    version="4.0.0",
    description=(
        "AI-powered voice and document assistant with real-time transcription, "
        "meeting summarization, and RAG-based document chat."
    ),
    lifespan=lifespan,
)


# -- CORS ---------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -- Routers ------------------------------------------------------------------

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


# -- Health / Root -------------------------------------------------------------


@app.get("/")
async def root():
    """API health check endpoint."""
    return {
        "name": "Kontext Agent",
        "version": "4.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
