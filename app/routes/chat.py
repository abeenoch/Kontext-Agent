from fastapi import APIRouter
from pydantic import BaseModel
from app.services.rag_pipeline import retrive_for_query
from app.services.llm_agent import query_llm,handle_llm_response

router = APIRouter()

class ChatRequest(BaseModel):
    query: str
    user_id: str

@router.post("/query", summary="Query the chat agent")
async def chat(req:ChatRequest):
    context = retrive_for_query(req.query)
    prompt = f"Context:\n{context}\n\nUser: {req.query}\n\nAnswer clearly. If an action is needed, return JSON with 'action' and 'payload'."
    llm_resp = query_llm(prompt)
    result = handle_llm_response(llm_resp)
    return result