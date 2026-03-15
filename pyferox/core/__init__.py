"""Core primitives for transport-agnostic service applications."""

from pyferox.core.app import App
from pyferox.core.di import ResolutionError, Scope, provider, singleton
from pyferox.core.handlers import handle, listen
from pyferox.core.messages import Command, Event, Query
from pyferox.core.module import Module

__all__ = [
    "App",
    "Command",
    "Event",
    "Module",
    "Query",
    "ResolutionError",
    "Scope",
    "handle",
    "listen",
    "provider",
    "singleton",
]
