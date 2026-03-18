"""Composable module definition."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from pyferox.core.di import Provider
from pyferox.core.handlers import HandlerFn, HandlerRegistry
from pyferox.core.middleware import Middleware

LifecycleHook = Callable[[], Awaitable[None] | None]
InitHook = Callable[[], None]


@dataclass(slots=True)
class ModuleDefinition:
    name: str = ""
    commands: list[type[Any]] = field(default_factory=list)
    queries: list[type[Any]] = field(default_factory=list)
    exports: list[type[Any]] = field(default_factory=list)
    handlers: list[HandlerFn] = field(default_factory=list)
    listeners: list[HandlerFn] = field(default_factory=list)
    providers: list[Provider] = field(default_factory=list)
    middlewares: list[Middleware] = field(default_factory=list)
    imports: list["Module"] = field(default_factory=list)
    on_init: list[InitHook] = field(default_factory=list)
    on_startup: list[LifecycleHook] = field(default_factory=list)
    on_shutdown: list[LifecycleHook] = field(default_factory=list)


@dataclass(slots=True)
class Module(ModuleDefinition):
    """Unit of composition for application features."""

    def load(self, registry: HandlerRegistry) -> None:
        self.validate_imports()
        declared_contracts = set(self.commands) | set(self.queries)
        for fn in self.handlers:
            message_type = getattr(fn, "__pyferox_handle__", None)
            if message_type is None:
                raise ValueError(f"Handler is missing @handle decorator: {fn}")
            if declared_contracts and message_type not in declared_contracts:
                raise ValueError(
                    f"Handler contract {message_type} is not declared in module '{self.name or '<anonymous>'}'"
                )
            registry.register_handler(message_type, fn)

        for fn in self.listeners:
            event_type = getattr(fn, "__pyferox_listen__", None)
            if event_type is None:
                raise ValueError(f"Listener is missing @listen decorator: {fn}")
            registry.register_listener(event_type, fn)

    def declared_contracts(self) -> tuple[type[Any], ...]:
        return tuple(dict.fromkeys([*self.commands, *self.queries]))

    def exported_contracts(self) -> tuple[type[Any], ...]:
        if self.exports:
            return tuple(dict.fromkeys(self.exports))
        return self.declared_contracts()

    def imported_contracts(self) -> tuple[type[Any], ...]:
        imported: list[type[Any]] = []
        for module in self.imports:
            imported.extend(module.exported_contracts())
        return tuple(dict.fromkeys(imported))

    def validate_imports(self) -> None:
        imported = set(self.imported_contracts())
        local_handlers = {
            message_type
            for message_type in (getattr(handler, "__pyferox_handle__", None) for handler in self.handlers)
            if message_type is not None
        }

        for contract in self.declared_contracts():
            if contract in local_handlers:
                continue
            if contract not in imported:
                raise ValueError(
                    f"Module '{self.name or '<anonymous>'}' declares contract {contract} without local handler "
                    "and without importing a module that exports it."
                )

        allowed_exports = set(self.declared_contracts()) | imported
        for contract in self.exports:
            if contract not in allowed_exports:
                raise ValueError(
                    f"Module '{self.name or '<anonymous>'}' exports contract {contract} "
                    "that is neither declared locally nor exported by imports."
                )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "commands": [contract.__name__ for contract in self.commands],
            "queries": [contract.__name__ for contract in self.queries],
            "exports": [contract.__name__ for contract in self.exported_contracts()],
            "imported_exports": [contract.__name__ for contract in self.imported_contracts()],
            "handlers": [handler.__name__ for handler in self.handlers],
            "listeners": [listener.__name__ for listener in self.listeners],
            "providers": [provider.key.__name__ for provider in self.providers],
            "imports": [module.name for module in self.imports],
            "middlewares": [type(middleware).__name__ for middleware in self.middlewares],
        }


def as_module(
    *,
    name: str = "",
    commands: Iterable[type[Any]] = (),
    queries: Iterable[type[Any]] = (),
    exports: Iterable[type[Any]] = (),
    handlers: Iterable[HandlerFn] = (),
    listeners: Iterable[HandlerFn] = (),
    providers: Iterable[Provider] = (),
    middlewares: Iterable[Middleware] = (),
    imports: Iterable[Module] = (),
    on_init: Iterable[InitHook] = (),
    on_startup: Iterable[LifecycleHook] = (),
    on_shutdown: Iterable[LifecycleHook] = (),
) -> Module:
    return Module(
        name=name,
        commands=list(commands),
        queries=list(queries),
        exports=list(exports),
        handlers=list(handlers),
        listeners=list(listeners),
        providers=list(providers),
        middlewares=list(middlewares),
        imports=list(imports),
        on_init=list(on_init),
        on_startup=list(on_startup),
        on_shutdown=list(on_shutdown),
    )


def module_diagnostics(modules: Iterable[Module]) -> list[dict[str, Any]]:
    return [module.diagnostics() for module in modules]
