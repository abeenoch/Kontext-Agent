from collections import defaultdict
from datetime import datetime

chat_history_store = {}

def add_message(user_id:str, role:str, content:str):
    if user_id not in chat_history_store:
        chat_history_store[user_id] = []
    chat_history_store[user_id].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat()
    })

def get_recent_history(user_id: str, limit: int = 5):
    """Return the most recent chat messages safely."""
    if user_id not in chat_history_store:
        chat_history_store[user_id] = []
    return chat_history_store[user_id][-limit:]


def clear_history(user_id: str):
    chat_history_store[user_id] = []

