import app.routes.docs as docs_routes


def test_docs_upload_chat_clear(client, auth_headers, monkeypatch):
    async def fake_ingest_file(_user_id, _filename, _content):
        return 2

    async def fake_retrieve_docs(_user_id, _query):
        return ["knowledge chunk"]

    async def fake_query_llm(_prompt, *args, **kwargs):
        return "mocked docs response"

    monkeypatch.setattr(docs_routes, "ingest_file", fake_ingest_file)
    monkeypatch.setattr(docs_routes, "retrieve_docs", fake_retrieve_docs)
    monkeypatch.setattr(docs_routes, "query_llm", fake_query_llm)

    files = {"file": ("notes.txt", b"hello world", "text/plain")}
    upload = client.post("/docs/upload", headers=auth_headers, files=files)
    assert upload.status_code == 200, upload.text
    udata = upload.json()
    assert udata["status"] == "ingested"
    assert udata["chunks_ingested"] == 2

    chat = client.post(
        "/docs/chat",
        headers=auth_headers,
        json={"query": "summarize", "use_rag": True},
    )
    assert chat.status_code == 200, chat.text
    cdata = chat.json()
    assert cdata["response"] == "mocked docs response"
    assert cdata["sources_used"] is True

    clear = client.delete("/docs/clear", headers=auth_headers)
    assert clear.status_code == 200, clear.text
    assert clear.json()["status"] == "cleared"
