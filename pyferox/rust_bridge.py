from __future__ import annotations

from functools import lru_cache

import pyferox_rust as _rust


def validate_compiled(compiled_schema, data: dict):
    return _rust.validate_compiled(compiled_schema, data)


def validate_partial_compiled(compiled_schema, data: dict):
    return _rust.validate_partial_compiled(compiled_schema, data)


def validate_query_compiled(compiled_schema, data: dict[str, str]):
    return _rust.validate_query_compiled(compiled_schema, data)


def serialize_json(data) -> str:
    return _rust.serialize_json(data)


def parse_path_params(pattern: str, path: str):
    return _rust.parse_path_params(pattern, path)


def compile_schema(schema: dict[str, str]):
    return _compile_schema_cached(_schema_key(schema))


def rust_validation_mode() -> str:
    return "rust-compiled"


def compiled_schema_cache_size() -> int:
    return _compile_schema_cached.cache_info().currsize


@lru_cache(maxsize=2048)
def _compile_schema_cached(schema_key: tuple[tuple[str, str], ...]):
    schema = dict(schema_key)
    return _rust.compile_schema(schema)


def _schema_key(schema: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(k), str(v)) for k, v in schema.items()))
