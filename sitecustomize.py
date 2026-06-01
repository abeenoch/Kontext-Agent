"""Process-wide compatibility shims loaded by Python at startup."""

import os

os.environ.setdefault("PYDANTIC_DISABLE_PLUGINS", "1")

try:  # pragma: no cover - startup shim
    import opentelemetry.sdk._logs as _otel_logs

    if not hasattr(_otel_logs, "LogData"):
        class _LogData:
            pass

        _otel_logs.LogData = _LogData

    if not hasattr(_otel_logs, "ReadableLogRecord"):
        class _ReadableLogRecord:
            pass

        _otel_logs.ReadableLogRecord = _ReadableLogRecord
except Exception:
    pass
