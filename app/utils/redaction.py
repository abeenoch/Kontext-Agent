import re
from typing import Optional

# Simple regex-based PII scrubbing. Not perfect but reduces obvious leaks before
# sending text to external LLMs or integrations.
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d[\s\-()]?){7,}\d")
CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


def redact_pii(text: Optional[str]) -> str:
    if not text:
        return ""
    cleaned = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    cleaned = PHONE_RE.sub("[REDACTED_PHONE]", cleaned)
    cleaned = CARD_RE.sub("[REDACTED_NUMBER]", cleaned)
    return cleaned
