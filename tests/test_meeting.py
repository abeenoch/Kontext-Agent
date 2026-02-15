import uuid
from asyncio import run

from app.services.chat_memory import save_meeting_chunk, save_meeting_summary


def test_meeting_summary_and_transcript_endpoints(client, auth_headers):
    meeting_id = f"smoke-{uuid.uuid4().hex[:8]}"

    run(save_meeting_chunk(meeting_id, "First point discussed"))
    run(save_meeting_chunk(meeting_id, "Second point discussed"))
    run(save_meeting_summary(meeting_id, "## Overview\n- Test summary"))

    summary = client.get(f"/meeting/{meeting_id}/summary", headers=auth_headers)
    assert summary.status_code == 200, summary.text
    assert "Overview" in (summary.json().get("summary") or "")

    transcript = client.get(f"/meeting/{meeting_id}/transcript", headers=auth_headers)
    assert transcript.status_code == 200, transcript.text
    assert "First point" in transcript.json()["transcript"]
