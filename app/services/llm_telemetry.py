from __future__ import annotations

from contextlib import suppress

from app.config import get_settings
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

try:  # pragma: no cover - optional dependency
    from prometheus_client import Counter, Gauge, Histogram
except Exception:  # pragma: no cover - graceful fallback when deps are absent
    Counter = Gauge = Histogram = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
except Exception:  # pragma: no cover - graceful fallback when deps are absent
    trace = None  # type: ignore[assignment]
    Resource = None  # type: ignore[assignment]
    TracerProvider = None  # type: ignore[assignment]
    BatchSpanProcessor = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
except Exception:  # pragma: no cover - graceful fallback when deps are absent
    OTLPSpanExporter = None  # type: ignore[assignment]

_tracing_configured = False

if Histogram is not None:
    LLM_REQUEST_DURATION = Histogram(
        "kontext_llm_request_duration_seconds",
        "Wall-clock duration for LLM calls.",
        ["provider", "model", "status"],
        buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60),
    )
    LLM_TTFT = Histogram(
        "kontext_llm_ttft_seconds",
        "Time to first token for LLM calls.",
        ["provider", "model"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
    )
    LLM_TOKENS_PER_SECOND = Histogram(
        "kontext_llm_tokens_per_second",
        "Generation speed after the first token.",
        ["provider", "model"],
        buckets=(0.5, 1, 2, 5, 10, 20, 40, 80, 160),
    )
    LLM_COST_USD = Counter(
        "kontext_llm_cost_usd_total",
        "Estimated LLM spend in USD.",
        ["provider", "model"],
    )
    LLM_TOKENS = Counter(
        "kontext_llm_tokens_total",
        "LLM tokens processed, labeled by token type.",
        ["provider", "model", "token_type"],
    )
    LLM_ERRORS = Counter(
        "kontext_llm_errors_total",
        "Total failed LLM calls.",
        ["provider", "model", "error_type"],
    )
    LLM_IN_FLIGHT = Gauge(
        "kontext_llm_in_flight",
        "Number of active LLM calls.",
        ["provider", "model"],
    )
else:  # pragma: no cover - fallback path
    LLM_REQUEST_DURATION = None
    LLM_TTFT = None
    LLM_TOKENS_PER_SECOND = None
    LLM_COST_USD = None
    LLM_TOKENS = None
    LLM_ERRORS = None
    LLM_IN_FLIGHT = None


def configure_tracing() -> bool:
    """Configure an OTLP trace pipeline when the optional dependencies exist."""
    global _tracing_configured
    if _tracing_configured:
        return True

    if settings.app_env == "test":
        logger.info("Skipping OpenTelemetry setup in test mode")
        _tracing_configured = True
        return False

    if not settings.otel_traces_enabled:
        logger.info("OpenTelemetry tracing disabled by configuration")
        _tracing_configured = True
        return False

    if trace is None or TracerProvider is None or OTLPSpanExporter is None:
        logger.info("OpenTelemetry packages unavailable; tracing will remain disabled")
        _tracing_configured = True
        return False

    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.otel_service_name})
        if Resource is not None
        else None
    )

    exporter = None
    if settings.otel_exporter_otlp_endpoint:
        exporter = OTLPSpanExporter(
            endpoint=settings.otel_exporter_otlp_endpoint,
            headers=dict(
                part.split("=", 1)
                for part in settings.otel_exporter_otlp_headers.split(",")
                if "=" in part
            )
            if settings.otel_exporter_otlp_headers
            else None,
        )
    else:
        exporter = OTLPSpanExporter()

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracing_configured = True
    logger.info("OpenTelemetry tracing configured")
    return True


def get_tracer(name: str):
    if trace is None:
        return None
    return trace.get_tracer(name)


def record_llm_success(
    *,
    provider: str,
    model: str,
    latency_seconds: float,
    ttft_seconds: float | None,
    tokens_per_second: float | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
    cost_usd: float | None,
) -> None:
    if LLM_REQUEST_DURATION is not None:
        LLM_REQUEST_DURATION.labels(provider, model, "success").observe(latency_seconds)
    if ttft_seconds is not None and LLM_TTFT is not None:
        LLM_TTFT.labels(provider, model).observe(ttft_seconds)
    if tokens_per_second is not None and LLM_TOKENS_PER_SECOND is not None:
        LLM_TOKENS_PER_SECOND.labels(provider, model).observe(tokens_per_second)
    if LLM_TOKENS is not None:
        if prompt_tokens is not None:
            LLM_TOKENS.labels(provider, model, "prompt").inc(prompt_tokens)
        if completion_tokens is not None:
            LLM_TOKENS.labels(provider, model, "completion").inc(completion_tokens)
        if total_tokens is not None:
            LLM_TOKENS.labels(provider, model, "total").inc(total_tokens)
    if cost_usd is not None and LLM_COST_USD is not None:
        LLM_COST_USD.labels(provider, model).inc(cost_usd)


def record_llm_error(*, provider: str, model: str, error_type: str, latency_seconds: float) -> None:
    if LLM_REQUEST_DURATION is not None:
        LLM_REQUEST_DURATION.labels(provider, model, "error").observe(latency_seconds)
    if LLM_ERRORS is not None:
        LLM_ERRORS.labels(provider, model, error_type).inc()


def llm_call_in_flight(provider: str, model: str):
    if LLM_IN_FLIGHT is None:
        return suppress()
    return LLM_IN_FLIGHT.labels(provider, model).track_inprogress()
