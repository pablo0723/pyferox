"""Composable module definition."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from pyferox.core.di import Provider
from pyferox.core.handlers import HandlerFn, HandlerRegistry

LifecycleHook = Callable[[], Awaitable[None] | None]
InitHook = Callable[[], None]


@dataclass(slots=True)
class Module:
    """Unit of composition for application features."""

    name: str = ""
    handlers: list[HandlerFn] = field(default_factory=list)
    listeners: list[HandlerFn] = field(default_factory=list)
    providers: list[Provider] = field(default_factory=list)
    imports: list["Module"] = field(default_factory=list)
    on_init: list[InitHook] = field(default_factory=list)
    on_startup: list[LifecycleHook] = field(default_factory=list)
    on_shutdown: list[LifecycleHook] = field(default_factory=list)

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
    name: str = "",
    handlers: Iterable[HandlerFn] = (),
    listeners: Iterable[HandlerFn] = (),
    providers: Iterable[Provider] = (),
    imports: Iterable[Module] = (),
    on_init: Iterable[InitHook] = (),
    on_startup: Iterable[LifecycleHook] = (),
    on_shutdown: Iterable[LifecycleHook] = (),
) -> Module:
    return Module(
        name=name,
        handlers=list(handlers),
        listeners=list(listeners),
        providers=list(providers),
        imports=list(imports),
        on_init=list(on_init),
        on_startup=list(on_startup),
        on_shutdown=list(on_shutdown),
    )
