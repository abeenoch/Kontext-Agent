from fastapi import APIRouter, HTTPException, Response, status

from app.services.llm_telemetry import LLM_REQUEST_DURATION

try:  # pragma: no cover - optional dependency
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
except Exception:  # pragma: no cover - graceful fallback when deps are absent
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    generate_latest = None

router = APIRouter(tags=["Metrics"])


@router.get("/metrics")
async def metrics() -> Response:
    if generate_latest is None or LLM_REQUEST_DURATION is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prometheus metrics are unavailable in this runtime.",
        )
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
