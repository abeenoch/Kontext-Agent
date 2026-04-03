import asyncio
import ssl

import httpx

from app.config import get_settings
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Reusable async client -- created once, shared across requests.
_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    """Return a module-level async HTTP client (lazy singleton)."""
    global _http_client
    if _http_client is None or getattr(_http_client, "is_closed", False):
        _http_client = httpx.AsyncClient(
            timeout=settings.llm_timeout,
            limits=httpx.Limits(
                max_keepalive_connections=5,
                keepalive_expiry=20,
            ),
            http2=False,  # keep HTTP/1.1 to avoid edge TLS/proxy issues
        )
    return _http_client


async def query_llm(
    prompt: str,
    max_retries: int = 3,
    temperature: float | None = None,
) -> str:
    """
    Query the Groq LLM with retry logic.

    Args:
        prompt: The user/system prompt text.
        max_retries: Number of retry attempts on transient failures.

    Returns:
        The LLM response text.

    Raises:
        ValueError: If the API key is missing or prompt is empty.
        RuntimeError: If all retries are exhausted.
    """
    if not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY environment variable not set")
    
    if not prompt or not prompt.strip():
        logger.warning("Empty prompt provided to LLM")
        return ""

    headers = {
        "Authorization": f"Bearer {settings.groq_api_key.strip()}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": settings.groq_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": settings.llm_temperature if temperature is None else temperature,
    }

    client = _get_http_client()
    last_exc: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.debug("Querying LLM (attempt %d/%d)", attempt, max_retries)

            response = await client.post(
                settings.groq_url,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            choices = data.get("choices", [])
            if not choices:
                raise ValueError(f"Unexpected LLM response format: {data}")

            result = choices[0]["message"]["content"]
            logger.debug("LLM response received (%d chars)", len(result))
            return result

        except httpx.TimeoutException:
            logger.warning("LLM request timeout (attempt %d/%d)", attempt, max_retries)
            last_exc = TimeoutError("LLM request timed out")

        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 429:
                logger.warning(
                    "LLM rate limited (attempt %d/%d)", attempt, max_retries
                )
                last_exc = exc
            else:
                logger.error(
                    "LLM HTTP error: %d - %s",
                    status_code,
                    exc.response.text,
                )
                raise

        except (httpx.TransportError, ssl.SSLError) as exc:
            # Transient TLS/connection corruption (e.g., BAD_RECORD_MAC). Reset client and retry.
            logger.warning(
                "LLM transport/TLS error (attempt %d/%d): %s. Resetting client.",
                attempt,
                max_retries,
                exc,
            )
            last_exc = exc
            try:
                await client.aclose()
            except Exception:
                pass
            _http_client = None
            await asyncio.sleep(1)
            continue

        except RuntimeError as exc:
            # httpx raises RuntimeError("Cannot send a request, as the client has been closed.")
            if "client has been closed" in str(exc):
                logger.warning(
                    "LLM client was closed (attempt %d/%d). Recreating and retrying.",
                    attempt,
                    max_retries,
                )
                _http_client = None
                client = _get_http_client()
                last_exc = exc
                await asyncio.sleep(0.5)
                continue
            raise

        except Exception as exc:
            logger.error("Unexpected error querying LLM: %s", exc)
            raise

    raise RuntimeError(f"Failed to query LLM after {max_retries} retries: {last_exc}")
