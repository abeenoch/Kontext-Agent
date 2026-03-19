import re
from typing import Optional

from app.services.llm_agent import query_llm
from app.services.integrations_service import (
    send_meeting_summary_email,
    push_meeting_summary_to_notion,
)
from app.logger import get_logger

logger = get_logger(__name__)


async def process_meeting_request(
    user_message: str,
    meeting_summary: str,
) -> dict:
    """
    Process a user request related to a meeting.

    The agent decides whether to respond conversationally, send an email,
    or push to Notion based on the user's intent.

    Args:
        user_message: The user's message or question.
        meeting_summary: The meeting summary for context.

    Returns:
        dict with 'action' (str) and 'response' (str) keys.
    """
    prompt = (
        "You are a meeting assistant agent. Based on the user message and "
        "meeting summary below, decide the appropriate action.\n\n"
        "Rules:\n"
        "- If the user wants to email the summary, respond with:\n"
        "  ACTION: EMAIL <email_address>\n"
        "- If the user wants to push to Notion, respond with:\n"
        "  ACTION: NOTION\n"
        "- Otherwise, answer the user's question about the meeting.\n\n"
        f"Meeting Summary:\n{meeting_summary}\n\n"
        f"User: {user_message}\n\n"
        "Agent:"
    )

    try:
        response = await query_llm(prompt)

        # Check for action patterns
        email_match = re.search(
            r"ACTION:\s*EMAIL\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
            response,
        )

        if email_match:
            email = email_match.group(1)
            try:
                send_meeting_summary_email(
                    email, "Meeting Summary", meeting_summary
                )
                return {
                    "action": "email",
                    "response": f"Summary emailed to {email}.",
                }
            except Exception as exc:
                logger.error("Email error: %s", exc)
                return {
                    "action": "error",
                    "response": f"Failed to send email: {exc}",
                }

        if "ACTION: NOTION" in response.upper():
            try:
                push_meeting_summary_to_notion(meeting_summary, "Meeting Summary")
                return {
                    "action": "notion",
                    "response": "Summary pushed to Notion.",
                }
            except Exception as exc:
                logger.error("Notion error: %s", exc)
                return {
                    "action": "error",
                    "response": f"Failed to push to Notion: {exc}",
                }

        # Conversational response
        clean_response = re.sub(r"ACTION:\s*\w+", "", response).strip()
        return {
            "action": "chat",
            "response": clean_response or response,
        }

    except Exception as exc:
        logger.error("Meeting agent error: %s", exc, exc_info=True)
        return {
            "action": "error",
            "response": f"Agent error: {exc}",
        }
