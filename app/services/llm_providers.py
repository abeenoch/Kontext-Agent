from __future__ import annotations

import asyncio
import json
import ssl
import time
from dataclasses import dataclass

import httpx

from app.config import get_settings
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass(slots=True)
class LLMUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(slots=True)
class LLMCallResult:
    text: str
    provider: str
    model: str
    usage: LLMUsage
    latency_seconds: float
    ttft_seconds: float | None
    tokens_per_second: float | None
    cost_usd: float | None


class LLMProviderError(Exception):
    """Base error for provider calls."""


class LLMRetryableError(LLMProviderError):
    """An error that can be retried safely."""


class LLMTimeoutError(LLMRetryableError):
    """Provider call timed out."""


class LLMTransportError(LLMRetryableError):
    """Transport or TLS failure."""


class LLMHTTPError(LLMProviderError):
    def __init__(self, status_code: int, response_text: str, provider: str):
        super().__init__(f"{provider} returned HTTP {status_code}: {response_text}")
        self.status_code = status_code
        self.response_text = response_text
        self.provider = provider

    @property
    def retryable(self) -> bool:
        return self.status_code in {429, 502, 503, 504}


class BaseLLMProvider:
    name = "base"

    def __init__(self, model: str, timeout: float, max_tokens: int | None = None):
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self._client: httpx.AsyncClient | None = None

    def _client_options(self) -> dict:
        return {
            "timeout": self.timeout,
            "limits": httpx.Limits(max_keepalive_connections=5, keepalive_expiry=20),
            "http2": False,
        }

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def _build_messages(self, prompt: str, system_prompt: str | None = None) -> list[dict]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _payload(
        self, prompt: str, temperature: float, system_prompt: str | None = None
    ) -> dict:
        payload = {
            "model": self.model,
            "messages": self._build_messages(prompt, system_prompt),
            "temperature": temperature,
            "stream": True,
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        return payload

    def _cost(self, prompt_tokens: int | None, completion_tokens: int | None) -> float:
        return 0.0

    def _tokens_per_second(
        self, completion_tokens: int | None, latency_seconds: float, ttft_seconds: float | None
    ) -> float | None:
        if not completion_tokens:
            return None
        generation_seconds = latency_seconds
        if ttft_seconds is not None:
            generation_seconds = max(latency_seconds - ttft_seconds, 1e-6)
        return completion_tokens / max(generation_seconds, 1e-6)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or getattr(self._client, "is_closed", False):
            self._client = httpx.AsyncClient(**self._client_options())
        return self._client

    async def close(self) -> None:
        if self._client is not None and not getattr(self._client, "is_closed", False):
            await self._client.aclose()
        self._client = None

    async def reset_client(self) -> None:
        await self.close()

    async def generate(
        self, prompt: str, temperature: float, system_prompt: str | None = None
    ) -> LLMCallResult:
        raise NotImplementedError


class GroqProvider(BaseLLMProvider):
    name = "groq"

    def __init__(self) -> None:
        super().__init__(
            settings.groq_model,
            settings.llm_timeout,
            getattr(settings, "llm_max_tokens", None),
        )

    def _headers(self) -> dict[str, str]:
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY environment variable not set")
        return {
            "Authorization": f"Bearer {settings.groq_api_key.strip()}",
            "Content-Type": "application/json",
        }

    def _payload(
        self, prompt: str, temperature: float, system_prompt: str | None = None
    ) -> dict:
        payload = super()._payload(prompt, temperature, system_prompt=system_prompt)
        payload["stream_options"] = {"include_usage": True}
        return payload

    def _cost(self, prompt_tokens: int | None, completion_tokens: int | None) -> float:
        prompt_tokens = prompt_tokens or 0
        completion_tokens = completion_tokens or 0
        return (
            (prompt_tokens * settings.groq_input_cost_per_1k_tokens / 1000.0)
            + (completion_tokens * settings.groq_output_cost_per_1k_tokens / 1000.0)
        )

    async def generate(
        self, prompt: str, temperature: float, system_prompt: str | None = None
    ) -> LLMCallResult:
        client = await self._get_client()
        started = time.perf_counter()
        first_token_at: float | None = None
        text_parts: list[str] = []
        usage = LLMUsage()

        try:
            async with client.stream(
                "POST",
                settings.groq_url,
                headers=self._headers(),
                json=self._payload(prompt, temperature, system_prompt=system_prompt),
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise LLMHTTPError(
                        response.status_code,
                        body.decode("utf-8", errors="replace"),
                        self.name,
                    )

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue

                    data = line.removeprefix("data:").strip()
                    if not data or data == "[DONE]":
                        continue

                    chunk = json.loads(data)
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue

                    delta = choices[0].get("delta") or {}
                    content = delta.get("content") or ""
                    if content:
                        if first_token_at is None:
                            first_token_at = time.perf_counter()
                        text_parts.append(content)

                    chunk_usage = chunk.get("usage") or {}
                    if chunk_usage:
                        usage.prompt_tokens = chunk_usage.get("prompt_tokens", usage.prompt_tokens)
                        usage.completion_tokens = chunk_usage.get(
                            "completion_tokens", usage.completion_tokens
                        )
                        usage.total_tokens = chunk_usage.get("total_tokens", usage.total_tokens)

        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(str(exc)) from exc
        except (httpx.TransportError, ssl.SSLError) as exc:
            raise LLMTransportError(str(exc)) from exc

        latency_seconds = time.perf_counter() - started
        text = "".join(text_parts).strip()
        if usage.total_tokens is None and (
            usage.prompt_tokens is not None or usage.completion_tokens is not None
        ):
            usage.total_tokens = (usage.prompt_tokens or 0) + (usage.completion_tokens or 0)

        ttft_seconds = None if first_token_at is None else first_token_at - started
        tokens_per_second = self._tokens_per_second(
            usage.completion_tokens, latency_seconds, ttft_seconds
        )

        return LLMCallResult(
            text=text,
            provider=self.name,
            model=self.model,
            usage=usage,
            latency_seconds=latency_seconds,
            ttft_seconds=ttft_seconds,
            tokens_per_second=tokens_per_second,
            cost_usd=self._cost(usage.prompt_tokens, usage.completion_tokens),
        )


class OllamaProvider(BaseLLMProvider):
    name = "ollama"

    def __init__(self) -> None:
        super().__init__(
            settings.ollama_model,
            settings.ollama_timeout,
            getattr(settings, "llm_max_tokens", None),
        )

    def _client_options(self) -> dict:
        options = super()._client_options()
        options["base_url"] = settings.ollama_base_url.rstrip("/")
        return options

    def _cost(self, prompt_tokens: int | None, completion_tokens: int | None) -> float:
        prompt_tokens = prompt_tokens or 0
        completion_tokens = completion_tokens or 0
        return (
            (prompt_tokens * settings.ollama_input_cost_per_1k_tokens / 1000.0)
            + (completion_tokens * settings.ollama_output_cost_per_1k_tokens / 1000.0)
        )

    def _payload(
        self, prompt: str, temperature: float, system_prompt: str | None = None
    ) -> dict:
        options = {"temperature": temperature}
        if self.max_tokens is not None:
            options["num_predict"] = self.max_tokens
        payload = {
            "model": self.model,
            "messages": self._build_messages(prompt, system_prompt),
            "stream": True,
            "options": options,
        }
        keep_alive = settings.ollama_keep_alive.strip()
        if keep_alive:
            payload["keep_alive"] = keep_alive
        return payload

    async def generate(
        self, prompt: str, temperature: float, system_prompt: str | None = None
    ) -> LLMCallResult:
        client = await self._get_client()
        started = time.perf_counter()
        first_token_at: float | None = None
        text_parts: list[str] = []
        usage = LLMUsage()

        url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"

        try:
            async with client.stream(
                "POST",
                url,
                json=self._payload(prompt, temperature, system_prompt=system_prompt),
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise LLMHTTPError(
                        response.status_code,
                        body.decode("utf-8", errors="replace"),
                        self.name,
                    )

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    chunk = json.loads(line)
                    message = chunk.get("message") or {}
                    content = message.get("content") or ""
                    if content:
                        if first_token_at is None:
                            first_token_at = time.perf_counter()
                        text_parts.append(content)

                    if chunk.get("done"):
                        usage.prompt_tokens = chunk.get("prompt_eval_count", usage.prompt_tokens)
                        usage.completion_tokens = chunk.get(
                            "eval_count", usage.completion_tokens
                        )
                        if usage.prompt_tokens is not None and usage.completion_tokens is not None:
                            usage.total_tokens = usage.prompt_tokens + usage.completion_tokens

        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(str(exc)) from exc
        except (httpx.TransportError, ssl.SSLError) as exc:
            raise LLMTransportError(str(exc)) from exc

        latency_seconds = time.perf_counter() - started
        text = "".join(text_parts).strip()
        if usage.total_tokens is None and (
            usage.prompt_tokens is not None or usage.completion_tokens is not None
        ):
            usage.total_tokens = (usage.prompt_tokens or 0) + (usage.completion_tokens or 0)

        ttft_seconds = None if first_token_at is None else first_token_at - started
        tokens_per_second = self._tokens_per_second(
            usage.completion_tokens, latency_seconds, ttft_seconds
        )

        return LLMCallResult(
            text=text,
            provider=self.name,
            model=self.model,
            usage=usage,
            latency_seconds=latency_seconds,
            ttft_seconds=ttft_seconds,
            tokens_per_second=tokens_per_second,
            cost_usd=self._cost(usage.prompt_tokens, usage.completion_tokens),
        )


_provider: BaseLLMProvider | None = None
_provider_name: str | None = None


def get_llm_provider() -> BaseLLMProvider:
    """Return a cached provider instance based on the configured backend."""
    global _provider, _provider_name

    provider_name = settings.llm_provider.strip().lower() or "groq"
    if _provider is not None and _provider_name == provider_name:
        return _provider

    if provider_name == "groq":
        _provider = GroqProvider()
    elif provider_name == "ollama":
        _provider = OllamaProvider()
    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER '{settings.llm_provider}'. Use 'groq' or 'ollama'."
        )

    _provider_name = provider_name
    logger.info("Using LLM provider: %s (%s)", _provider.name, _provider.model)
    return _provider


async def close_llm_provider() -> None:
    """Close the cached provider client, if any."""
    global _provider, _provider_name
    if _provider is not None:
        await _provider.close()
    _provider = None
    _provider_name = None
