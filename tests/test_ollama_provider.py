from types import SimpleNamespace


def test_ollama_payload_includes_keep_alive(monkeypatch):
    from app.services import llm_providers

    monkeypatch.setattr(
        llm_providers,
        "settings",
        SimpleNamespace(
            ollama_model="phi3:mini",
            ollama_timeout=30.0,
            ollama_base_url="http://localhost:11434",
            ollama_keep_alive="30m",
            ollama_input_cost_per_1k_tokens=0.0,
            ollama_output_cost_per_1k_tokens=0.0,
        ),
    )

    provider = llm_providers.OllamaProvider()
    payload = provider._payload("Summarize the meeting", 0.2)

    assert payload["stream"] is True
    assert payload["options"]["temperature"] == 0.2
    assert payload["keep_alive"] == "30m"
