"""Structured logging hooks for request/message execution."""

from __future__ import annotations

import logging
from typing import Any

from pyferox.core.app import App
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


class AppLifecycleLoggingHooks:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or get_logger()

    async def on_startup(self) -> None:
        self.logger.info("app.startup")

    async def on_shutdown(self) -> None:
        self.logger.info("app.shutdown")

    async def on_exception(self, context: ExecutionContext, message: Any, exc: Exception) -> None:
        self.logger.exception(
            "dispatch.error",
            extra={"request_id": context.request_id, "trace_id": context.trace_id, "message": type(message).__name__},
        )


def install_logging_hooks(
    app: App,
    *,
    logger: logging.Logger | None = None,
    include_request_middleware: bool = True,
) -> AppLifecycleLoggingHooks:
    hooks = AppLifecycleLoggingHooks(logger=logger)
    app.add_startup_hook(hooks.on_startup)
    app.add_shutdown_hook(hooks.on_shutdown)
    app.add_exception_hook(hooks.on_exception)
    if include_request_middleware:
        app.add_middleware(RequestLoggingMiddleware(logger=hooks.logger))
    return hooks
