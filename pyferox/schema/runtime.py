"""Typed input parsing and output serialization backed by msgspec."""

from __future__ import annotations

import inspect
import re
from dataclasses import is_dataclass
from typing import Any, ClassVar, Generic, TypeVar, get_origin, get_type_hints

import msgspec

from pyferox.core.errors import ValidationError
from pyferox.core.messages import Message, is_message_type
from pyferox.core.results import Streamed, to_payload

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")

_PATH_ERROR_RE = re.compile(r"^(?P<message>.+?) - at `\$(?P<path>[^`]*)`$")
_MISSING_FIELD_RE = re.compile(r"^Object missing required field `(?P<field>[^`]+)`$")
_UNKNOWN_FIELD_RE = re.compile(r"^Object contains unknown field `(?P<field>[^`]+)`$")


class SchemaModel(msgspec.Struct, forbid_unknown_fields=True):
    """Preferred strict schema base for external payloads."""


class Schema(SchemaModel):
    """Alias for schema contracts to keep public API semantic."""


class DTO(SchemaModel):
    """Alias for response/data transfer contracts."""


def schema_metadata(**metadata: Any):
    """Attach schema metadata for docs and diagnostics."""

    def decorator(schema_type: type[Any]) -> type[Any]:
        setattr(schema_type, "__pyferox_schema_metadata__", dict(metadata))
        return schema_type

    return decorator


def get_schema_metadata(schema_or_type: Any) -> dict[str, Any]:
    schema_type = schema_or_type if isinstance(schema_or_type, type) else type(schema_or_type)
    metadata = getattr(schema_type, "__pyferox_schema_metadata__", {})
    return dict(metadata)


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
    if _is_message_contract(schema_type):
        parsed = _parse_message_contract(schema_type, payload, error_message=error_message)
        _apply_validation_hooks(schema_type, parsed, error_message=error_message)
        return parsed
    if _is_schema_model(schema_type) and isinstance(payload, dict):
        issues = _schema_model_field_issues(schema_type, payload)
        if issues:
            raise ValidationError(error_message, details=issues)
    try:
        parsed = msgspec.convert(payload, type=schema_type, strict=False)
        _apply_validation_hooks(schema_type, parsed, error_message=error_message)
        return parsed
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
    if issubclass(schema_type, Message):
        return False
    if issubclass(schema_type, (str, int, float, bool, bytes, bytearray, list, tuple, set, dict)):
        return False
    return True


def _is_message_contract(schema_type: type[Any]) -> bool:
    return (
        inspect.isclass(schema_type)
        and is_message_type(schema_type)
        and not issubclass(schema_type, msgspec.Struct)
    )


def _parse_message_contract(schema_type: type[Message], payload: Any, *, error_message: str) -> Any:
    contract_schema = _get_contract_schema(schema_type)
    try:
        parsed = msgspec.convert(payload, type=contract_schema, strict=False)
    except msgspec.ValidationError as exc:
        raise ValidationError(error_message, details=_details_from_msgspec_error(exc)) from exc
    data = msgspec.to_builtins(parsed)
    if is_dataclass(schema_type):
        try:
            return msgspec.convert(data, type=schema_type, strict=False)
        except msgspec.ValidationError as exc:
            raise ValidationError(error_message, details=_details_from_msgspec_error(exc)) from exc

    try:
        return schema_type(**data)
    except TypeError:
        instance = schema_type.__new__(schema_type)
        for key, value in data.items():
            setattr(instance, key, value)
        return instance


def _get_contract_schema(schema_type: type[Message]) -> type[msgspec.Struct]:
    cached = getattr(schema_type, "__pyferox_contract_schema__", None)
    if cached is not None:
        return cached

    hints = get_type_hints(schema_type, include_extras=True)
    fields: list[tuple[Any, ...]] = []
    for name, annotation in hints.items():
        if name.startswith("_"):
            continue
        if get_origin(annotation) is ClassVar:
            continue
        default = getattr(schema_type, name, msgspec.NODEFAULT)
        if default is msgspec.NODEFAULT:
            fields.append((name, annotation))
        else:
            fields.append((name, annotation, default))
    struct_name = f"{schema_type.__name__}Contract"
    contract_schema = msgspec.defstruct(struct_name, fields, forbid_unknown_fields=True)
    setattr(schema_type, "__pyferox_contract_schema__", contract_schema)
    return contract_schema


def _is_schema_model(schema_type: type[Any]) -> bool:
    return inspect.isclass(schema_type) and issubclass(schema_type, SchemaModel)


def _apply_validation_hooks(schema_type: type[Any], value: Any, *, error_message: str) -> None:
    instance_validator = getattr(value, "__validate__", None)
    if callable(instance_validator):
        result = instance_validator()
        if inspect.isawaitable(result):  # pragma: no cover
            raise ValidationError(f"{error_message}: async validators are not supported in parse_input")
        if isinstance(result, dict):
            raise ValidationError(error_message, details={str(k): str(v) for k, v in result.items()})

    class_validator = getattr(schema_type, "validate_payload", None)
    if callable(class_validator):
        result = class_validator(value)
        if inspect.isawaitable(result):  # pragma: no cover
            raise ValidationError(f"{error_message}: async validators are not supported in parse_input")
        if isinstance(result, dict):
            raise ValidationError(error_message, details={str(k): str(v) for k, v in result.items()})


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
