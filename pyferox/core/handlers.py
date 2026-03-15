"""Decorators and registries for handlers/listeners."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

HandlerFn = Callable[..., Awaitable[Any]]


def handle(message_type: type[Any]) -> Callable[[HandlerFn], HandlerFn]:
    """Mark a coroutine as a command/query handler."""

    def decorator(fn: HandlerFn) -> HandlerFn:
        setattr(fn, "__pyferox_handle__", message_type)
        return fn

    return decorator


def listen(event_type: type[Any]) -> Callable[[HandlerFn], HandlerFn]:
    """Mark a coroutine as an event listener."""

    def decorator(fn: HandlerFn) -> HandlerFn:
        setattr(fn, "__pyferox_listen__", event_type)
        return fn

    return decorator


@dataclass(slots=True)
class HandlerRegistry:
    """Maps message/event types to callables."""

    message_handlers: dict[type[Any], HandlerFn] = field(default_factory=dict)
    event_listeners: dict[type[Any], list[HandlerFn]] = field(default_factory=dict)

    def register_handler(self, message_type: type[Any], fn: HandlerFn) -> None:
        if message_type in self.message_handlers:
            existing = self.message_handlers[message_type]
            raise ValueError(f"Handler already registered for {message_type}: {existing}")
        self.message_handlers[message_type] = fn

    def register_listener(self, event_type: type[Any], fn: HandlerFn) -> None:
        self.event_listeners.setdefault(event_type, []).append(fn)

    def get_handler(self, message_type: type[Any]) -> HandlerFn | None:
        return self.message_handlers.get(message_type)

    def get_listeners(self, event_type: type[Any]) -> list[HandlerFn]:
        return list(self.event_listeners.get(event_type, []))

