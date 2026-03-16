from __future__ import annotations

import asyncio
import logging

import pytest

from pyferox.core import ExecutionContext
from pyferox.logging import RequestLoggingMiddleware, get_logger


def test_get_logger_reuses_existing_handler() -> None:
    logger_name = "pyferox.tests.logging"
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()

    first = get_logger(logger_name)
    second = get_logger(logger_name)
    assert first is second
    assert len(second.handlers) == 1


class CaptureLogger:
    def __init__(self) -> None:
        self.info_calls: list[tuple[str, dict[str, object]]] = []
        self.exception_calls: list[tuple[str, dict[str, object]]] = []

    def info(self, message: str, *, extra: dict[str, object]) -> None:
        self.info_calls.append((message, extra))

    def exception(self, message: str, *, extra: dict[str, object]) -> None:
        self.exception_calls.append((message, extra))


def test_request_logging_middleware_logs_success() -> None:
    capture = CaptureLogger()
    middleware = RequestLoggingMiddleware(logger=capture)  # type: ignore[arg-type]
    context = ExecutionContext(request_id="r1", trace_id="t1")

    async def call_next(message: object) -> str:
        return "ok"

    result = asyncio.run(middleware(context, object(), call_next))
    assert result == "ok"
    assert [entry[0] for entry in capture.info_calls] == ["request.start", "request.end"]
    assert capture.exception_calls == []


def test_request_logging_middleware_logs_exception() -> None:
    capture = CaptureLogger()
    middleware = RequestLoggingMiddleware(logger=capture)  # type: ignore[arg-type]
    context = ExecutionContext(request_id="r2", trace_id="t2")

    async def call_next(message: object) -> str:
        raise ValueError("boom")

    with pytest.raises(ValueError):
        asyncio.run(middleware(context, object(), call_next))
    assert [entry[0] for entry in capture.info_calls] == ["request.start"]
    assert [entry[0] for entry in capture.exception_calls] == ["request.error"]
