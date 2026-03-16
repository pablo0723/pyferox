"""Typed input parsing and output serialization backed by msgspec."""

from __future__ import annotations

import inspect
import re
from dataclasses import is_dataclass
from typing import Any, Generic, TypeVar

import msgspec

from pyferox.core.errors import ValidationError
from pyferox.core.results import Streamed, to_payload

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")

_PATH_ERROR_RE = re.compile(r"^(?P<message>.+?) - at `\$(?P<path>[^`]*)`$")
_MISSING_FIELD_RE = re.compile(r"^Object missing required field `(?P<field>[^`]+)`$")
_UNKNOWN_FIELD_RE = re.compile(r"^Object contains unknown field `(?P<field>[^`]+)`$")


class SchemaModel(msgspec.Struct, forbid_unknown_fields=True):
    """Preferred strict schema base for external payloads."""


class TypedSchema(Generic[TIn, TOut]):
    def __init__(self, input_type: type[TIn], output_type: type[TOut] | None = None) -> None:
        self.input_type = input_type
        self.output_type = output_type

    def parse(self, payload: Any) -> TIn:
        return parse_input(self.input_type, payload)

    def dump(self, value: Any) -> Any:
        serialized = serialize_output(value)
        if self.output_type is None:
            return serialized
        validated = parse_input(self.output_type, serialized, error_message="Output validation failed")
        return serialize_output(validated)


def parse_input(
    schema_type: type[Any],
    payload: Any,
    *,
    error_message: str = "Input validation failed",
) -> Any:
    if _is_schema_model(schema_type) and isinstance(payload, dict):
        issues = _schema_model_field_issues(schema_type, payload)
        if issues:
            raise ValidationError(error_message, details=issues)
    try:
        return msgspec.convert(payload, type=schema_type, strict=False)
    except msgspec.ValidationError as exc:
        fallback = _try_construct_from_kwargs(schema_type, payload)
        if fallback is not None:
            return fallback
        raise ValidationError(error_message, details=_details_from_msgspec_error(exc)) from exc
    except TypeError as exc:
        fallback = _try_construct_from_kwargs(schema_type, payload)
        if fallback is not None:
            return fallback
        raise ValidationError(f"Unable to parse input for {schema_type}: {exc}") from exc


def serialize_output(value: Any) -> Any:
    value = to_payload(value)
    if isinstance(value, Streamed):
        return value
    try:
        return msgspec.to_builtins(value)
    except Exception as exc:
        if hasattr(value, "__dict__"):
            try:
                return msgspec.to_builtins(value.__dict__)
            except Exception:
                pass
        raise ValidationError(f"Unable to serialize output for value: {type(value)}") from exc


def format_validation_error(exc: ValidationError) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": "validation_error", "error": str(exc)}
    if exc.details:
        payload["details"] = exc.details
    return payload


def _details_from_msgspec_error(exc: msgspec.ValidationError) -> dict[str, str]:
    message = str(exc)
    missing_match = _MISSING_FIELD_RE.match(message)
    if missing_match is not None:
        return {missing_match.group("field"): "Field is required"}

    unknown_match = _UNKNOWN_FIELD_RE.match(message)
    if unknown_match is not None:
        return {unknown_match.group("field"): "Unexpected field"}

    path_match = _PATH_ERROR_RE.match(message)
    if path_match is not None:
        path = _normalize_path(path_match.group("path"))
        return {path: path_match.group("message")}

    return {"input": message}


def _normalize_path(raw_path: str) -> str:
    path = raw_path.lstrip(".").replace("[", ".").replace("]", "").strip(".")
    return path or "input"


def _try_construct_from_kwargs(schema_type: type[Any], payload: Any) -> Any | None:
    if not _supports_kwargs_fallback(schema_type, payload):
        return None
    try:
        return schema_type(**payload)
    except Exception:
        return None


def _supports_kwargs_fallback(schema_type: type[Any], payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if not inspect.isclass(schema_type):
        return False
    if is_dataclass(schema_type):
        return False
    if issubclass(schema_type, msgspec.Struct):
        return False
    if issubclass(schema_type, (str, int, float, bool, bytes, bytearray, list, tuple, set, dict)):
        return False
    return True


def _is_schema_model(schema_type: type[Any]) -> bool:
    return inspect.isclass(schema_type) and issubclass(schema_type, SchemaModel)


def _schema_model_field_issues(schema_type: type[SchemaModel], payload: dict[str, Any]) -> dict[str, str]:
    fields: tuple[str, ...] = schema_type.__struct_fields__
    defaults: tuple[Any, ...] = schema_type.__struct_defaults__
    required_fields = set(fields[: len(fields) - len(defaults)])

    payload_fields = set(payload)
    issues: dict[str, str] = {}
    for name in sorted(required_fields - payload_fields):
        issues[name] = "Field is required"
    for name in sorted(payload_fields - set(fields)):
        issues[name] = "Unexpected field"
    return issues
