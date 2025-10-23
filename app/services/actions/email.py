import os, requests

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
BREVO_SENDER = os.getenv("BREVO_SENDER_EMAIL")

def send_email(payload: dict):
    to = payload.get("to")
    subject = payload.get("subject", "Kontext Summary")
    body = payload.get("body", "")
    if not to:
        return {"ok": False, "error": "missing recipient"}

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {"api-key": BREVO_API_KEY, "Content-Type": "application/json"}
    data = {
        "sender": {"email": BREVO_SENDER},
        "to": [{"email": to}],
        "subject": subject,
        "htmlContent": f"<html><body>{body}</body></html>"
    }
    resp = requests.post(url, headers=headers, json=data)
    return {"ok": resp.status_code == 201, "status_code": resp.status_code, "text": resp.text}
