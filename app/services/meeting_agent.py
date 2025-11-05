import re
from app.services.integrations_service import (
    send_meeting_summary_email,
    push_meeting_summary_to_notion
)
from app.services.voice_stream import generate_llm_reply


async def agent_chat(user_message: str, summary: str):
    """
    Lightweight agent that interprets post-meeting user requests.
    Uses the LLM to decide whether to send email, push to Notion,
    or just reply conversationally.
    """

    decision_prompt = f"""
    You are an AI Meeting Assistant.

    The meeting summary is:
    ---
    {summary}
    ---

    The user said: "{user_message}"

    You can do the following:
    1. Send an email with the meeting summary.
    2. Push the meeting summary to Notion.
    3. Respond conversationally.

    If the user wants to send email, respond in this exact format:
    ACTION:EMAIL to=<comma-separated emails> subject=<subject> body=<body>

    If they want to push to Notion, respond:
    ACTION:NOTION title=<title> content=<content>

    Otherwise, reply with a natural conversational message.
    """

    llm_output = await generate_llm_reply(decision_prompt)

    # 
    if "ACTION:EMAIL" in llm_output:
        match = re.search(r"to=(.*?) subject=(.*?) body=(.*)", llm_output)
        if match:
            to = match.group(1).strip()
            subject = match.group(2).strip()
            body = match.group(3).strip()
            send_meeting_summary_email(to, subject, body)
            return f"Email sent to {to}"
        else:
            return "I detected you want to send an email, but I need the recipient’s address."

    elif "ACTION:NOTION" in llm_output:
        match = re.search(r"title=(.*?) content=(.*)", llm_output)
        if match:
            title = match.group(1).strip()
            content = match.group(2).strip()
            push_meeting_summary_to_notion(content, title)
            return f"Added to Notion as '{title}'"
        else:
            return "I can add this to Notion — what title should I use?"

    else:
        return llm_output
