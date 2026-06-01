from __future__ import annotations

import asyncio
import time

from app.config import get_settings
from app.logger import get_logger
from app.services.llm_providers import (
    LLMHTTPError,
    LLMProviderError,
    LLMRetryableError,
    LLMTransportError,
    close_llm_provider,
    get_llm_provider,
)
from app.services.llm_telemetry import (
    get_tracer,
    llm_call_in_flight,
    record_llm_error,
    record_llm_success,
)

logger = get_logger(__name__)
settings = get_settings()


def _retry_delay_seconds(attempt: int) -> float:
    return min(2 ** (attempt - 1), 8.0)


async def query_llm_detailed(
    prompt: str,
    max_retries: int = 3,
    temperature: float | None = None,
):
    """
    Query the configured LLM backend and return the full telemetry payload.
    """
    if not prompt or not prompt.strip():
        logger.warning("Empty prompt provided to LLM")
        return None

    provider = get_llm_provider()
    effective_temperature = settings.llm_temperature if temperature is None else temperature
    tracer = get_tracer(__name__)

    last_exc: Exception | None = None

    for attempt in range(1, max_retries + 1):
        started = time.perf_counter()
        if tracer is not None:
            span = tracer.start_span("llm.call")
            span.set_attribute("llm.provider", provider.name)
            span.set_attribute("llm.model", provider.model)
            span.set_attribute("llm.attempt", attempt)
            span.set_attribute("llm.prompt.length_chars", len(prompt))
        else:
            span = None

        try:
            with llm_call_in_flight(provider.name, provider.model):
                result = await provider.generate(prompt, effective_temperature)

            if span is not None:
                span.set_attribute("llm.status", "success")
                span.set_attribute("llm.latency_seconds", result.latency_seconds)
                if result.ttft_seconds is not None:
                    span.set_attribute("llm.ttft_seconds", result.ttft_seconds)
                if result.tokens_per_second is not None:
                    span.set_attribute("llm.tokens_per_second", result.tokens_per_second)
                if result.usage.prompt_tokens is not None:
                    span.set_attribute("llm.prompt_tokens", result.usage.prompt_tokens)
                if result.usage.completion_tokens is not None:
                    span.set_attribute("llm.completion_tokens", result.usage.completion_tokens)
                if result.usage.total_tokens is not None:
                    span.set_attribute("llm.total_tokens", result.usage.total_tokens)
                if result.cost_usd is not None:
                    span.set_attribute("llm.estimated_cost_usd", result.cost_usd)

            record_llm_success(
                provider=result.provider,
                model=result.model,
                latency_seconds=result.latency_seconds,
                ttft_seconds=result.ttft_seconds,
                tokens_per_second=result.tokens_per_second,
                prompt_tokens=result.usage.prompt_tokens,
                completion_tokens=result.usage.completion_tokens,
                total_tokens=result.usage.total_tokens,
                cost_usd=result.cost_usd,
            )

            if span is not None:
                span.end()
            return result

        except LLMHTTPError as exc:
            last_exc = exc
            latency_seconds = time.perf_counter() - started
            if span is not None:
                span.set_attribute("llm.status", "http_error")
                span.set_attribute("http.status_code", exc.status_code)
                span.record_exception(exc)
                span.end()

            record_llm_error(
                provider=provider.name,
                model=provider.model,
                error_type=f"http_{exc.status_code}",
                latency_seconds=latency_seconds,
            )

            if exc.retryable and attempt < max_retries:
                await asyncio.sleep(_retry_delay_seconds(attempt))
                continue
            raise

        except LLMTransportError as exc:
            last_exc = exc
            latency_seconds = time.perf_counter() - started
            if span is not None:
                span.set_attribute("llm.status", "transport_error")
                span.record_exception(exc)
                span.end()

            record_llm_error(
                provider=provider.name,
                model=provider.model,
                error_type=type(exc).__name__,
                latency_seconds=latency_seconds,
            )

            await provider.reset_client()
            if attempt < max_retries:
                await asyncio.sleep(_retry_delay_seconds(attempt))
                continue
            raise

        except LLMRetryableError as exc:
            last_exc = exc
            latency_seconds = time.perf_counter() - started
            if span is not None:
                span.set_attribute("llm.status", "retryable_error")
                span.record_exception(exc)
                span.end()

            record_llm_error(
                provider=provider.name,
                model=provider.model,
                error_type=type(exc).__name__,
                latency_seconds=latency_seconds,
            )

            await provider.reset_client()
            if attempt < max_retries:
                await asyncio.sleep(_retry_delay_seconds(attempt))
                continue
            raise RuntimeError(
                f"Failed to query LLM after {max_retries} retries: {last_exc}"
            ) from exc

        except LLMProviderError as exc:
            latency_seconds = time.perf_counter() - started
            if span is not None:
                span.set_attribute("llm.status", "provider_error")
                span.record_exception(exc)
                span.end()

            record_llm_error(
                provider=provider.name,
                model=provider.model,
                error_type=type(exc).__name__,
                latency_seconds=latency_seconds,
            )
            raise

        except Exception as exc:
            latency_seconds = time.perf_counter() - started
            if span is not None:
                span.set_attribute("llm.status", "unexpected_error")
                span.record_exception(exc)
                span.end()
            record_llm_error(
                provider=provider.name,
                model=provider.model,
                error_type=type(exc).__name__,
                latency_seconds=latency_seconds,
            )
            raise

    raise RuntimeError(f"Failed to query LLM after {max_retries} retries: {last_exc}")


async def query_llm(
    prompt: str,
    max_retries: int = 3,
    temperature: float | None = None,
) -> str:
    """
    Query the configured LLM backend and return just the text payload.
    """
    result = await query_llm_detailed(
        prompt,
        max_retries=max_retries,
        temperature=temperature,
    )
    if result is None:
        return ""
    return result.text


async def close_query_llm_client() -> None:
    """Close the cached provider client during shutdown."""
    await close_llm_provider()
