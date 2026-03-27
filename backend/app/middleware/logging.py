"""Structured JSON logging middleware with per-request correlation IDs."""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings

# ── Context variable shared across the request lifecycle ────────────
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="-")


class CorrelationIDFilter(logging.Filter):
    """Inject ``correlation_id`` into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_ctx.get("-")
        return True


def configure_logging() -> None:
    """Set up structured JSON-style logging for the entire application.

    Call once during startup (inside the lifespan handler).
    """
    log_format = (
        '{"time":"%(asctime)s","level":"%(levelname)s",'
        '"correlation_id":"%(correlation_id)s",'
        '"name":"%(name)s","message":"%(message)s"}'
    )
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(log_format, datefmt="%Y-%m-%dT%H:%M:%S%z"))
    handler.addFilter(CorrelationIDFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL)

    # Quiet noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.DEBUG if settings.LOG_LEVEL == "DEBUG" else logging.WARNING
    )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to every request and log request/response
    details as structured JSON.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Use an existing header or generate a fresh UUID4
        cid = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        correlation_id_ctx.set(cid)

        logger = logging.getLogger("http")
        start = time.perf_counter()

        logger.info(
            "request_start method=%s path=%s client=%s",
            request.method,
            request.url.path,
            request.client.host if request.client else "-",
        )

        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled exception during request processing")
            raise

        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Correlation-ID"] = cid
        response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"

        logger.info(
            "request_end method=%s path=%s status=%d duration_ms=%.1f",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )

        return response
