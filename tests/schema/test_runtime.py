from __future__ import annotations

from dataclasses import dataclass

import pytest

from pyferox.core.errors import ValidationError
from pyferox.schema import TypedSchema, format_validation_error, parse_input, serialize_output


@dataclass(slots=True)
class Input:
    user_id: int
    name: str


def test_parse_input_with_type_coercion() -> None:
    parsed = parse_input(Input, {"user_id": "1", "name": "Ann"})
    assert parsed == Input(user_id=1, name="Ann")


def test_parse_input_validation_error() -> None:
    with pytest.raises(ValidationError):
        parse_input(Input, {"user_id": "x", "name": "Ann"})


def test_serialize_output() -> None:
    payload = serialize_output(Input(user_id=2, name="Bob"))
    assert payload == {"user_id": 2, "name": "Bob"}


def test_typed_schema_and_error_formatting() -> None:
    schema = TypedSchema(Input)
    parsed = schema.parse({"user_id": "3", "name": "Eve"})
    assert parsed.user_id == 3
    with pytest.raises(ValidationError) as exc:
        schema.parse({"user_id": "NaN", "name": "Eve"})
    payload = format_validation_error(exc.value)
    assert payload["error"] == "Input validation failed"
    assert payload["details"]["user_id"]
