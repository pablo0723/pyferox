"""Message markers used by command/query/event handlers."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, ClassVar, Mapping


class Message:
    """Base contract type for command/query/event messages."""

    __contract_metadata__: ClassVar[dict[str, Any]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        inherited = getattr(cls, "__contract_metadata__", {})
        cls.__contract_metadata__ = dict(inherited)

    @classmethod
    def metadata(cls) -> Mapping[str, Any]:
        return MappingProxyType(cls.__contract_metadata__)

    @classmethod
    def set_metadata(cls, **metadata: Any) -> None:
        cls.__contract_metadata__.update(metadata)


class Command(Message):
    """Base type for write-side operations."""


class Query(Message):
    """Base type for read-side operations."""


class Event(Message):
    """Base type for domain/integration events."""


def contract(**metadata: Any):
    """Attach optional framework metadata to a command/query/event contract."""

    def decorator(message_type: type[Message]) -> type[Message]:
        if not issubclass(message_type, Message):
            raise TypeError(f"@contract expects a Message subtype, got: {message_type}")
        message_type.set_metadata(**metadata)
        return message_type

    return decorator


def get_contract_metadata(message_or_type: Message | type[Message]) -> Mapping[str, Any]:
    message_type = message_or_type if isinstance(message_or_type, type) else type(message_or_type)
    if not issubclass(message_type, Message):
        return {}
    return message_type.metadata()


def is_message_type(candidate: Any) -> bool:
    return isinstance(candidate, type) and issubclass(candidate, Message)
