import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from notion_client import Client

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_PAGE_ID = os.getenv("NOTION_PAGE_ID") 
notion = Client(auth=NOTION_TOKEN)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = 587
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")

def send_meeting_summary_email(to_email: str, subject: str, summary: str):
    """
    Send a meeting summary email.
    """
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = to_email
        msg["Subject"] = subject

        msg.attach(MIMEText(summary, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)

        print(f"Email sent to {to_email}")

    except Exception as e:
        print(f"Error sending email: {e}")




def push_meeting_summary_to_notion(summary: str, meeting_title: str = "New Meeting"):
    """
    Create a Notion page under a parent (database or page) with the meeting summary.
    """
    try:
        notion.pages.create(
            parent={"page_id": NOTION_PAGE_ID},
            properties={
                "title": {
                    "title": [{"text": {"content": meeting_title}}],
                }
            },
            children=[
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"text": {"content": summary}}]},
                }
            ],
        )
        print(f"Summary pushed to Notion page")
    except Exception as e:
        print(f"Error pushing to Notion: {e}")
