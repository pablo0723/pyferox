from __future__ import annotations

from typing import get_args, get_origin

from .errors import HTTPError
from .rust_bridge import compile_schema, validate_compiled, validate_query_compiled


class Schema:
    __spec_cache__: dict[str, str] | None = None
    __compiled_spec_cache__ = None

    @classmethod
    def _spec(cls) -> dict[str, str]:
        if cls.__spec_cache__ is not None:
            return cls.__spec_cache__
        annotations = getattr(cls, "__annotations__", {})
        spec = {}
        for field_name, field_type in annotations.items():
            spec[field_name] = _type_to_name(field_type)
        cls.__spec_cache__ = spec
        return spec

    @classmethod
    def _compiled_spec(cls):
        if cls.__compiled_spec_cache__ is None:
            cls.__compiled_spec_cache__ = compile_schema(cls._spec())
        return cls.__compiled_spec_cache__

    @classmethod
    def validate(cls, data: dict):
        if not isinstance(data, dict):
            raise HTTPError(422, "payload must be an object")
        try:
            return validate_compiled(cls._compiled_spec(), data)
        except ValueError as exc:
            raise HTTPError(422, "validation failed", {"reason": str(exc)}) from exc

    @classmethod
    def validate_query(cls, query_params: dict[str, str]):
        out = {}
        rust_input = {}
        for field_name, type_name in cls._spec().items():
            if field_name not in query_params:
                raise HTTPError(422, "validation failed", {"reason": f"missing query param: {field_name}"})
            raw = query_params[field_name]
            rust_input[field_name] = raw
        try:
            return validate_query_compiled(cls._compiled_spec(), rust_input)
        except ValueError as exc:
            raise HTTPError(422, "validation failed", {"reason": str(exc)}) from exc


def _type_to_name(field_type) -> str:
    if field_type in (str, int, float, bool, dict, list):
        return field_type.__name__
    origin = get_origin(field_type)
    if origin in (list, dict):
        return origin.__name__
    if origin is not None:
        args = get_args(field_type)
        non_none = [arg for arg in args if arg is not type(None)]
        if len(non_none) == 1 and len(non_none) != len(args):
            return _type_to_name(non_none[0])
    raise TypeError(f"Unsupported schema field type: {field_type!r}")
