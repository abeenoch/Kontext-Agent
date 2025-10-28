from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from app.routes import docs,chat
from dotenv import load_dotenv
from app.services.chat_memory import init_db
from app.routes import docs, chat, voice, meeting


load_dotenv()
app = FastAPI(title="Kontext Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(docs.router)
app.include_router(chat.router)
app.include_router(voice.router)
app.include_router(meeting.router)


@app.on_event("startup")
async def startup_event():
    await init_db()

@app.get("/")
async def root():
    return {"message": "Welcome to Kontext Agent API"}