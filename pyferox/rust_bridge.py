from __future__ import annotations

import asyncio
import json
from functools import lru_cache

import pyferox_rust as _rust


def validate_compiled(compiled_schema, data: dict):
    return _rust.validate_compiled(compiled_schema, data)


def validate_partial_compiled(compiled_schema, data: dict):
    return _rust.validate_partial_compiled(compiled_schema, data)


def validate_query_compiled(compiled_schema, data: dict[str, str]):
    return _rust.validate_query_compiled(compiled_schema, data)


async def validate_compiled_async(compiled_schema, data: dict):
    return await asyncio.to_thread(_rust.validate_compiled, compiled_schema, data)


async def validate_partial_compiled_async(compiled_schema, data: dict):
    return await asyncio.to_thread(_rust.validate_partial_compiled, compiled_schema, data)


async def validate_query_compiled_async(compiled_schema, data: dict[str, str]):
    return await asyncio.to_thread(_rust.validate_query_compiled, compiled_schema, data)


def serialize_json(data) -> str:
    return _rust.serialize_json(data)


def parse_path_params(pattern: str, path: str):
    return _rust.parse_path_params(pattern, path)


def compile_schema(schema: dict[str, str]):
    return _compile_schema_cached(_schema_key(schema))


def compile_schema_with_rules(schema: dict[str, str], rules: dict[str, dict]):
    return _compile_schema_with_rules_cached(_schema_key(schema), _rules_key(rules))


def rust_validation_mode() -> str:
    return "rust-compiled"


def compiled_schema_cache_size() -> int:
    return _compile_schema_cached.cache_info().currsize


@lru_cache(maxsize=2048)
def _compile_schema_cached(schema_key: tuple[tuple[str, str], ...]):
    schema = dict(schema_key)
    return _rust.compile_schema(schema)


@lru_cache(maxsize=2048)
def _compile_schema_with_rules_cached(
    schema_key: tuple[tuple[str, str], ...],
    rules_key: tuple[tuple[str, str], ...],
):
    schema = dict(schema_key)
    rules = {field: json.loads(payload) for field, payload in rules_key}
    return _rust.compile_schema_with_rules(schema, rules)


def _schema_key(schema: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(k), str(v)) for k, v in schema.items()))


def _rules_key(rules: dict[str, dict]) -> tuple[tuple[str, str], ...]:
    normalized: list[tuple[str, str]] = []
    for field, payload in sorted(rules.items(), key=lambda kv: kv[0]):
        normalized.append((str(field), json.dumps(payload, sort_keys=True, separators=(",", ":"))))
    return tuple(normalized)
