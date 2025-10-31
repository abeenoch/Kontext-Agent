import time
from app.services.llm_agent import query_llm

async def summarize_periodically(transcript_path: str, websocket):
    """
    Every 10 minutes, summarize ongoing transcript.
    """
    while True:
        await asyncio.sleep(600)  # 10 minutes
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                text = f.read()

            if len(text) < 200:
                continue

            summary_prompt = (
                "Summarize the past 10 minutes of this meeting. "
                "Focus on main discussion points, decisions, and next steps.\n\n"
                f"{text[-4000:]}"  # last ~4K chars
            )
            summary = query_llm(summary_prompt)
            await websocket.send_json({
                "type": "summary_update",
                "timestamp": time.strftime("%H:%M"),
                "summary": summary
            })
        except Exception as e:
            print(f"[Summary task error] {e}")
