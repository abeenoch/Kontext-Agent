import asyncio

from app.auth import verify_token
from app.config import get_settings
from app.services.chat_memory import save_meeting_chunk


class _FakeDeepgramHandler:
    def __init__(self, *args, **kwargs):
        self.is_connected = True
        self.sample_rate = kwargs.get("sample_rate", 16000)

    async def connect(self, on_transcript=None, on_error=None):
        self.is_connected = True
        return True

    async def disconnect(self):
        self.is_connected = False

    async def finish(self):
        self.is_connected = False

    async def keepalive(self):
        return None

    def seconds_since_last_activity(self):
        return 0.0

    async def send_audio(self, _pcm_data):
        return True


def test_meeting_stop_cancels_periodic_before_final_summary(client, auth_headers, monkeypatch):
    from app.routes import meeting as meeting_route

    state = {"periodic_cancelled": False, "final_called": False}

    async def fake_summarize_periodically(*args, **kwargs):
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            state["periodic_cancelled"] = True
            raise

    async def fake_query_llm(prompt: str, *args, **kwargs):
        state["final_called"] = True
        assert state["periodic_cancelled"], (
            "Periodic summary task must be cancelled before final summary starts."
        )
        return "## Overview\n- Final summary generated from transcript."

    monkeypatch.setattr(meeting_route, "DeepgramSTTHandler", _FakeDeepgramHandler)
    monkeypatch.setattr(meeting_route, "summarize_periodically", fake_summarize_periodically)
    monkeypatch.setattr(meeting_route, "query_llm", fake_query_llm)

    token = auth_headers["Authorization"].split(" ", 1)[1]
    user_id = verify_token(token)
    meeting_id = "stopflow01"

    settings = get_settings()
    # Seed the DB with a transcript chunk so final summary path has content.
    asyncio.run(save_meeting_chunk(user_id, meeting_id, "Long transcript line for final summary. " * 20))

    with client.websocket_connect(f"/meeting/ws?token={token}&meeting_id={meeting_id}") as ws:
        first = ws.receive_json()
        assert first["type"] == "connected"

        ws.send_text("STOP")

        got_final = False
        for _ in range(5):
            msg = ws.receive_json()
            if msg.get("type") == "final_summary":
                got_final = True
                break

        assert got_final, "Expected final_summary message after STOP"

    assert state["periodic_cancelled"], "Periodic summarizer should be cancelled on STOP"
    assert state["final_called"], "Final summary generator should be invoked after STOP"
