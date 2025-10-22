import os, json, requests

GROQ_KEY = os.getenv("GROQ_KEY")

def query_llm(prompt: str):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_KEY}"}
    data = {
        "model": "mixtral-8x7b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "max_tokens": 512
    }
    r = requests.post(url, headers=headers, json=data)
    return r.json()["choices"][0]["message"]["content"]

def handle_llm_response(text: str):
    try:
        start = text.index("{")
        action_obj = json.loads(text[start:])
    except Exception:
        return {"type": "answer", "response": text}

    action = action_obj.get("action")
    payload = action_obj.get("payload", {})

    if action == "email":
        from app.services.actions import email
        return email.send_email(payload)
    elif action == "notion":
        from app.services.actions import notion
        return notion.create_page(payload)
    elif action == "translate":
        from app.services.actions import translate
        return translate.translate_text(payload)
    elif action == "drive":
        from app.services.actions import drive
        return drive.upload_to_drive(payload)
    return {"type": "answer", "response": text}