import os, requests

NOTION_KEY = os.getenv("NOTION_KEY")
NOTION_DB_ID = os.getenv("NOTION_DB_ID")

def create_page(payload: dict):
    headers = {
        "Authorization": f"Bearer {NOTION_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    title = payload.get("title", "Kontext Note")
    content = payload.get("content", "")
    data = {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": {"Name": {"title": [{"text": {"content": title}}]}},
        "children": [{"object": "block", "type": "paragraph",
                      "paragraph": {"text": [{"type": "text", "text": {"content": content}}]}}]
    }
    r = requests.post("https://api.notion.com/v1/pages", headers=headers, json=data)
    return {"ok": r.ok, "response": r.text}
