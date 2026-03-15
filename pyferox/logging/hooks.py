"""Structured logging hooks for request/message execution."""

from __future__ import annotations

import logging
from typing import Any

from pyferox.core.context import ExecutionContext


def get_logger(name: str = "pyferox") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


class RequestLoggingMiddleware:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or get_logger()

    async def __call__(self, context: ExecutionContext, message: Any, call_next: Any) -> Any:
        self.logger.info(
            "request.start",
            extra={"request_id": context.request_id, "trace_id": context.trace_id, "message": type(message).__name__},
        )
        try:
            result = await call_next(message)
            self.logger.info(
                "request.end",
                extra={"request_id": context.request_id, "trace_id": context.trace_id, "message": type(message).__name__},
            )
            return result
        except Exception:
            self.logger.exception(
                "request.error",
                extra={"request_id": context.request_id, "trace_id": context.trace_id, "message": type(message).__name__},
            )
            raise

