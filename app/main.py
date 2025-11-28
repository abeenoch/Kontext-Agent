import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.database import db
from app.api.routes import router as api_router
from app.api.websocket import meeting_websocket_endpoint
from app.core.transcriber import transcriber

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Meeting Agent API...")
    await db.init_schema()
    logger.info(f"Database initialized at {settings.DB_PATH}")
    
    # Preload Whisper model
    logger.info("Preloading Whisper model...")
    await transcriber.initialize()
    logger.info("Whisper model loaded successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Meeting Agent API...")
    await db.close()


# Create FastAPI app
app = FastAPI(
    title="Meeting Agent API",
    description="Real-time meeting recording, transcription, and AI chat system",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


#
# HTTP REST API routes
app.include_router(api_router)



@app.websocket("/ws/meeting")
async def websocket_meeting(websocket: WebSocket):
    """WebSocket endpoint for meeting audio streaming."""
    await meeting_websocket_endpoint(websocket)


# 


from fastapi.responses import FileResponse
from pathlib import Path

@app.get("/")
async def root():
    """Serve HTML UI."""
    ui_path = Path(__file__).parent / "ui" / "index.html"
    if ui_path.exists():
        return FileResponse(ui_path)
    else:
        return {
            "service": "Meeting Agent API",
            "version": "1.0.0",
            "status": "running",
            "endpoints": {
                "websocket": "/ws/meeting",
                "api": "/api",
                "docs": "/docs"
            }
        }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "database": "connected"
    }



@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc)
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower()
    )