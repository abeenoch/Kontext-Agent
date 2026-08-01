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
            llm_max_tokens=256,
            ollama_input_cost_per_1k_tokens=0.0,
            ollama_output_cost_per_1k_tokens=0.0,
        ),
    )

    provider = llm_providers.OllamaProvider()
    payload = provider._payload("Summarize the meeting", 0.2)

    assert payload["stream"] is True
    assert payload["options"]["temperature"] == 0.2
    assert payload["options"]["num_predict"] == 256
    assert payload["keep_alive"] == "30m"


def test_ollama_payload_includes_system_message(monkeypatch):
    from app.services import llm_providers

    monkeypatch.setattr(
        llm_providers,
        "settings",
        SimpleNamespace(
            ollama_model="phi3:mini",
            ollama_timeout=30.0,
            ollama_base_url="http://localhost:11434",
            ollama_keep_alive="30m",
            llm_max_tokens=None,
            ollama_input_cost_per_1k_tokens=0.0,
            ollama_output_cost_per_1k_tokens=0.0,
        ),
    )

    provider = llm_providers.OllamaProvider()
    payload = provider._payload(
        "user content", 0.2, system_prompt="You are a helpful assistant."
    )

    assert payload["messages"] == [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "user content"},
    ]
