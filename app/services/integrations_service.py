import html
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from notion_client import Client
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from app.config import get_settings
from app.logger import get_logger
from app.validators import sanitize_html, validate_email

logger = get_logger(__name__)
settings = get_settings()


def _inline_markdown_to_html(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
    return escaped


def _markdown_summary_to_email_html(summary: str) -> str:
    lines = summary.splitlines()
    parts: list[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            parts.append("</ul>")
            in_list = False

    for raw in lines:
        line = raw.strip()
        if not line:
            close_list()
            continue

        if line.startswith("### "):
            close_list()
            parts.append(f"<h3>{_inline_markdown_to_html(line[4:])}</h3>")
            continue

        if line.startswith("## "):
            close_list()
            parts.append(f"<h2>{_inline_markdown_to_html(line[3:])}</h2>")
            continue

        if line.startswith("- "):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{_inline_markdown_to_html(line[2:])}</li>")
            continue

        close_list()
        parts.append(f"<p>{_inline_markdown_to_html(line)}</p>")

    close_list()

    body = "\n".join(parts) if parts else f"<p>{_inline_markdown_to_html(summary)}</p>"
    return (
        "<html><body style=\"font-family:Arial,sans-serif;color:#0f172a;line-height:1.5;\">"
        f"{body}"
        "</body></html>"
    )


def _notion_rich_text(content: str) -> list[dict]:
    content = content[:1900]
    return [{"type": "text", "text": {"content": content}}]


def _summary_to_notion_blocks(summary: str, max_blocks: int = 95) -> list[dict]:
    blocks: list[dict] = []

    for raw in summary.splitlines():
        line = raw.strip()
        if not line:
            continue

        if line.startswith("### "):
            blocks.append(
                {
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {"rich_text": _notion_rich_text(line[4:])},
                }
            )
        elif line.startswith("## "):
            blocks.append(
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {"rich_text": _notion_rich_text(line[3:])},
                }
            )
        elif line.startswith("- "):
            blocks.append(
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": _notion_rich_text(line[2:])},
                }
            )
        else:
            blocks.append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": _notion_rich_text(line)},
                }
            )

        if len(blocks) >= max_blocks:
            break

    if not blocks:
        blocks.append(
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": _notion_rich_text("No summary content available.")},
            }
        )

    return blocks


def send_meeting_summary_email(to_email: str, subject: str, summary: str) -> bool:
    """
    Send a meeting summary email.

    Args:
        to_email: Recipient email address
        subject: Email subject
        summary: Email body content (Markdown)

    Returns:
        True if successful, False otherwise
    """
    try:
        validate_email(to_email)

        if not settings.smtp_user or not settings.smtp_pass:
            logger.error("SMTP credentials not configured")
            return False

        email_html = _markdown_summary_to_email_html(summary)
        sanitized_summary = sanitize_html(email_html)

        msg = MIMEMultipart()
        msg["From"] = settings.smtp_user
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(sanitized_summary, "html"))

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_pass)
            server.send_message(msg)

        logger.info("Email sent successfully to %s", to_email)
        return True

    except ValueError as e:
        logger.error("Email validation error: %s", e)
        return False
    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP authentication failed - check credentials")
        return False
    except smtplib.SMTPException as e:
        logger.error("SMTP error: %s", e)
        return False
    except Exception as e:
        logger.error("Error sending email: %s", e, exc_info=True)
        return False


def send_password_reset_email(to_email: str, reset_token: str) -> bool:
    """
    Send a password reset email with a one-time token.

    If FRONTEND_URL is configured, include a deep link; otherwise include the token.
    """
    try:
        validate_email(to_email)
        if not settings.smtp_user or not settings.smtp_pass:
            logger.error("SMTP credentials not configured")
            return False

        reset_link = f"{settings.frontend_url.rstrip('/')}/reset-password?token={reset_token}"
        body = (
            f"<p>We received a request to reset your password.</p>"
            f"<p>Reset link: <a href=\"{reset_link}\">{reset_link}</a></p>"
            f"<p>If you did not request this, you can ignore this email.</p>"
        )

        msg = MIMEMultipart()
        msg["From"] = settings.smtp_user
        msg["To"] = to_email
        msg["Subject"] = "Reset your Kontext Agent password"
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_pass)
            server.send_message(msg)

        logger.info("Password reset email sent to %s", to_email)
        return True

    except Exception as exc:
        logger.error("Password reset email error: %s", exc, exc_info=True)
        return False


def push_meeting_summary_to_notion(summary: str, meeting_title: str = "New Meeting") -> bool:
    """
    Create a Notion page with structured blocks from summary Markdown.

    Args:
        summary: Meeting summary content
        meeting_title: Title for the Notion page

    Returns:
        True if successful, False otherwise
    """
    try:
        if not settings.notion_token or not settings.notion_page_id:
            logger.error("Notion credentials not configured")
            return False

        notion = Client(auth=settings.notion_token)
        children = _summary_to_notion_blocks(summary)

        notion.pages.create(
            parent={"page_id": settings.notion_page_id},
            properties={
                "title": {
                    "title": [{"text": {"content": meeting_title}}],
                }
            },
            children=children,
        )

        logger.info("Summary pushed to Notion page: %s", meeting_title)
        return True

    except Exception as e:
        logger.error("Error pushing to Notion: %s", e, exc_info=True)
        return False


def _summary_to_slack_blocks(summary: str, meeting_title: str) -> list[dict]:
    """
    Convert a Markdown meeting summary into Slack Block Kit blocks.

    Slack blocks give a nicely formatted message with a header, divider,
    and each Markdown section rendered as mrkdwn text.
    """
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":memo: {meeting_title}",
                "emoji": True,
            },
        },
        {"type": "divider"},
    ]

    # Accumulate lines into sections; flush when a heading is hit or at end.
    current_lines: list[str] = []

    def flush_section() -> None:
        text = "\n".join(current_lines).strip()
        if text:
            # Slack mrkdwn text field is capped at 3000 chars.
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": text[:3000]},
                }
            )
        current_lines.clear()

    for raw in summary.splitlines():
        line = raw.strip()
        if not line:
            continue

        if line.startswith("## "):
            flush_section()
            # Render h2 as bold heading line
            current_lines.append(f"*{line[3:].strip()}*")
        elif line.startswith("### "):
            flush_section()
            current_lines.append(f"_*{line[4:].strip()}*_")
        elif line.startswith("- "):
            current_lines.append(f"• {line[2:].strip()}")
        else:
            current_lines.append(line)

    flush_section()

    blocks.append({"type": "divider"})
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "_Sent by Kontext Agent_",
                }
            ],
        }
    )

    return blocks


def send_meeting_summary_to_slack(
    summary: str,
    meeting_title: str = "Meeting Summary",
    channel: str | None = None,
) -> bool:
    """
    Post a meeting summary to a Slack channel using Block Kit formatting.

    Args:
        summary: Meeting summary content (Markdown).
        meeting_title: Human-readable title shown in the Slack header.
        channel: Target Slack channel (e.g. ``#engineering``).
                 Falls back to ``settings.slack_default_channel`` when omitted.

    Returns:
        True if the message was posted successfully, False otherwise.
    """
    try:
        if not settings.slack_bot_token:
            logger.error("SLACK_BOT_TOKEN is not configured")
            return False

        target_channel = (channel or settings.slack_default_channel or "#general").strip()
        if not target_channel:
            logger.error("No Slack channel specified and SLACK_DEFAULT_CHANNEL is not set")
            return False

        client = WebClient(token=settings.slack_bot_token)
        blocks = _summary_to_slack_blocks(summary, meeting_title)

        client.chat_postMessage(
            channel=target_channel,
            text=f":memo: {meeting_title}",  # fallback text for notifications
            blocks=blocks,
        )

        logger.info("Meeting summary posted to Slack channel %s", target_channel)
        return True

    except SlackApiError as e:
        logger.error(
            "Slack API error posting to %s: %s",
            channel or settings.slack_default_channel,
            e.response["error"],
        )
        return False
    except Exception as e:
        logger.error("Error posting to Slack: %s", e, exc_info=True)
        return False
