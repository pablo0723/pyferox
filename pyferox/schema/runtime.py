"""Typed input parsing and output serialization."""

from __future__ import annotations

from dataclasses import asdict, fields, is_dataclass
from typing import Any, Generic, TypeVar, get_origin, get_type_hints

from pyferox.core.errors import ValidationError
from pyferox.core.results import to_payload

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")


class TypedSchema(Generic[TIn, TOut]):
    def __init__(self, input_type: type[TIn], output_type: type[TOut] | None = None) -> None:
        self.input_type = input_type
        self.output_type = output_type

    def parse(self, payload: dict[str, Any]) -> TIn:
        return parse_input(self.input_type, payload)

    def dump(self, value: Any) -> Any:
        serialized = serialize_output(value)
        if self.output_type is None:
            return serialized
        if not isinstance(serialized, dict):
            return serialized
        return parse_input(self.output_type, serialized)


def parse_input(schema_type: type[Any], payload: dict[str, Any]) -> Any:
    if not isinstance(payload, dict):
        raise ValidationError("Input payload must be an object")
    if is_dataclass(schema_type):
        return _parse_dataclass(schema_type, payload)
    try:
        return schema_type(**payload)
    except Exception as exc:
        raise ValidationError(f"Unable to parse input for {schema_type}: {exc}") from exc


def serialize_output(value: Any) -> Any:
    value = to_payload(value)
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (set, tuple)):
        return list(value)
    if hasattr(value, "__dict__"):
        return value.__dict__
    raise ValidationError(f"Unable to serialize output for value: {type(value)}")


def format_validation_error(exc: ValidationError) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": str(exc)}
    if exc.details:
        payload["details"] = exc.details
    return payload


def _parse_dataclass(schema_type: type[Any], payload: dict[str, Any]) -> Any:
    errors: dict[str, str] = {}
    kwargs: dict[str, Any] = {}
    hints = get_type_hints(schema_type)
    for field_info in fields(schema_type):
        if field_info.name not in payload:
            continue
        raw = payload[field_info.name]
        expected = hints.get(field_info.name, field_info.type)
        try:
            kwargs[field_info.name] = _coerce(expected, raw)
        except (TypeError, ValueError) as exc:
            errors[field_info.name] = str(exc)
    if errors:
        raise ValidationError("Input validation failed", details=errors)
    try:
        return schema_type(**kwargs)
    except TypeError as exc:
        raise ValidationError(str(exc)) from exc


def _coerce(expected_type: type[Any], value: Any) -> Any:
    origin = get_origin(expected_type)
    if origin in (list, dict, tuple, set):
        return value
    if expected_type is bool and isinstance(value, str):
        lowered = value.lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        raise ValueError(f"Cannot coerce '{value}' to bool")
    if expected_type in (str, int, float, bool):
        return expected_type(value)
    return value
