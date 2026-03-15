"""Execution middleware interfaces."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from pyferox.core.context import ExecutionContext

NextCallable = Callable[[Any], Awaitable[Any]]


class Middleware(Protocol):
    async def __call__(self, context: ExecutionContext, message: Any, call_next: NextCallable) -> Any:
        ...


def compose_middlewares(
    *,
    middlewares: list[Middleware],
    context: ExecutionContext,
    terminal: NextCallable,
) -> NextCallable:
    call_next = terminal
    for middleware in reversed(middlewares):
        previous = call_next

        async def call(msg: Any, mw: Middleware = middleware, nxt: NextCallable = previous) -> Any:
            return await mw(context, msg, nxt)

        call_next = call
    return call_next
