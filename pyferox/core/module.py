"""Composable module definition."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from pyferox.core.di import Provider
from pyferox.core.handlers import HandlerFn, HandlerRegistry


@dataclass(slots=True)
class Module:
    """Unit of composition for application features."""

    handlers: list[HandlerFn] = field(default_factory=list)
    listeners: list[HandlerFn] = field(default_factory=list)
    providers: list[Provider] = field(default_factory=list)

    def load(self, registry: HandlerRegistry) -> None:
        for fn in self.handlers:
            message_type = getattr(fn, "__pyferox_handle__", None)
            if message_type is None:
                raise ValueError(f"Handler is missing @handle decorator: {fn}")
            registry.register_handler(message_type, fn)

        for fn in self.listeners:
            event_type = getattr(fn, "__pyferox_listen__", None)
            if event_type is None:
                raise ValueError(f"Listener is missing @listen decorator: {fn}")
            registry.register_listener(event_type, fn)


def as_module(
    *,
    handlers: Iterable[HandlerFn] = (),
    listeners: Iterable[HandlerFn] = (),
    providers: Iterable[Provider] = (),
) -> Module:
    return Module(
        handlers=list(handlers),
        listeners=list(listeners),
        providers=list(providers),
    )

