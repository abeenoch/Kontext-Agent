from fastapi import APIRouter
from app.schemas.chat import ChatRequest
from app.services.llm_agent import query_llm
from app.services.chat_memory import add_message, get_recent_history
from app.services.rag_pipeline import retrieve_relevant_docs

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/query")
async def chat(request: ChatRequest):
    user_id = request.user_id
    prompt = request.query

    history = await get_recent_history(user_id)
    retrieved_docs = retrieve_relevant_docs(user_id, prompt)

    context_text = "\n".join([d["content"] for d in retrieved_docs])
    history_text = "\n".join([f"{h['role']}: {h['content']}" for h in history])

    full_prompt = f"""
You are Kontext Assistant. Use the following document context and chat history
to answer the user's question.

Chat History:
{history_text}

Relevant Context:
{context_text}

User Query:
{prompt}
    """.strip()

    llm_resp = query_llm(full_prompt)

    await add_message(user_id, "user", prompt)
    await add_message(user_id, "assistant", llm_resp)

    return {"response": llm_resp}
