import re
from typing import Optional
from fastapi import HTTPException, status


def validate_email(email: str) -> str:
    """Validate email format."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(pattern, email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid email format: {email}"
        )
    return email


def validate_emails(emails: str) -> list[str]:
    """Validate comma-separated emails."""
    email_list = [e.strip() for e in emails.split(",")]
    validated = []
    for email in email_list:
        if email:
            validated.append(validate_email(email))
    return validated


def validate_user_id(user_id: str) -> str:
    """Validate user_id format."""
    if not user_id or len(user_id) < 1 or len(user_id) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user_id format"
        )
    return user_id


def validate_file_size(file_size: int, max_size_mb: int = 50) -> int:
    """Validate file size."""
    max_bytes = max_size_mb * 1024 * 1024
    if file_size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds {max_size_mb}MB limit"
        )
    return file_size


def validate_file_type(filename: str, allowed_types: list[str]) -> str:
    """Validate file type by extension."""
    ext = filename.lower().split(".")[-1]
    if ext not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type .{ext} not allowed. Allowed types: {', '.join(allowed_types)}"
        )
    return filename


def sanitize_html(text: str) -> str:
    """Basic HTML sanitization."""
    # Remove script tags and dangerous attributes
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"on\w+\s*=", "", text, flags=re.IGNORECASE)
    return text


def validate_meeting_id(meeting_id: str) -> str:
    """
    Validate meeting_id for safe use in DB keys and filenames.

    Allows 8-64 chars from [A-Za-z0-9_-].
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", meeting_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid meeting_id format",
        )
    return meeting_id
