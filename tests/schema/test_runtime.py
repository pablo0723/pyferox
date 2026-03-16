from __future__ import annotations

from dataclasses import dataclass

import pytest

from pyferox.core.errors import ValidationError
from pyferox.schema import SchemaModel, TypedSchema, format_validation_error, parse_input, serialize_output


@dataclass(slots=True)
class Input:
    user_id: int
    name: str


class SchemaInput(SchemaModel):
    user_id: int
    name: str


@dataclass(slots=True)
class Address:
    city: str
    zip_code: int


@dataclass(slots=True)
class NestedInput:
    user_id: int
    tags: list[int]
    address: Address | None = None


def test_parse_input_with_type_coercion() -> None:
    parsed = parse_input(Input, {"user_id": "1", "name": "Ann"})
    assert parsed == Input(user_id=1, name="Ann")


def test_parse_input_validation_error() -> None:
    with pytest.raises(ValidationError):
        parse_input(Input, {"user_id": "x", "name": "Ann"})


def test_parse_input_reports_missing_and_unexpected_fields() -> None:
    with pytest.raises(ValidationError) as exc:
        parse_input(SchemaInput, {"name": "Ann", "extra": "boom"})
    payload = format_validation_error(exc.value)
    assert payload["type"] == "validation_error"
    assert payload["details"]["user_id"] == "Field is required"
    assert payload["details"]["extra"] == "Unexpected field"


def test_parse_input_nested_dataclass_and_collections() -> None:
    parsed = parse_input(
        NestedInput,
        {
            "user_id": "7",
            "tags": ["1", "2", "3"],
            "address": {"city": "Kyiv", "zip_code": "10101"},
        },
    )
    assert parsed.user_id == 7
    assert parsed.tags == [1, 2, 3]
    assert parsed.address == Address(city="Kyiv", zip_code=10101)


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
    assert payload["type"] == "validation_error"
    assert payload["error"] == "Input validation failed"
    assert payload["details"]["user_id"]


def test_typed_schema_dump_validates_and_serializes_output() -> None:
    schema = TypedSchema(SchemaInput, output_type=SchemaInput)
    dumped = schema.dump({"user_id": "10", "name": "Nia"})
    assert dumped == {"user_id": 10, "name": "Nia"}
