import app.routes.chat as chat_routes


def test_chat_query_and_clear_history(client, auth_headers, monkeypatch):
    async def fake_retrieve_docs(_user_id, _query):
        return ["doc context"]

    async def fake_query_llm(_prompt, *args, **kwargs):
        return "mocked chat response"

    monkeypatch.setattr(chat_routes, "retrieve_docs", fake_retrieve_docs)
    monkeypatch.setattr(chat_routes, "query_llm", fake_query_llm)

    response = client.post(
        "/chat/query",
        headers=auth_headers,
        json={"query": "What is the update?"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["response"] == "mocked chat response"
    assert data["sources_used"] is True

    cleared = client.delete("/chat/history", headers=auth_headers)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["status"] == "cleared"
