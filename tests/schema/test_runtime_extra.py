from __future__ import annotations

from dataclasses import dataclass

import msgspec
import pytest

from pyferox import Command, Query, contract, get_contract_metadata
from pyferox.core.errors import ValidationError
from pyferox.schema import TypedSchema, get_schema_metadata, parse_input, schema_metadata, serialize_output
from pyferox.schema import runtime as schema_runtime


class PlainModel:
    def __init__(self, value: int) -> None:
        self.value = value


class FailingPlainModel:
    def __init__(self, value: int, required: str) -> None:
        self.value = value
        self.required = required


def test_parse_input_fallback_to_kwargs_constructor() -> None:
    parsed = parse_input(PlainModel, {"value": 12})
    assert isinstance(parsed, PlainModel)
    assert parsed.value == 12


def test_parse_input_non_type_schema_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        parse_input("not-a-type", {"value": 1})  # type: ignore[arg-type]


def test_parse_input_non_dict_payload_disables_kwargs_fallback() -> None:
    with pytest.raises(ValidationError):
        parse_input(PlainModel, 1)


def test_parse_input_constructor_fallback_failure_surfaces_validation_error() -> None:
    with pytest.raises(ValidationError):
        parse_input(FailingPlainModel, {"value": 1})


def test_serialize_output_falls_back_to_dunder_dict() -> None:
    class Output:
        def __init__(self) -> None:
            self.ok = True

    payload = serialize_output(Output())
    assert payload == {"ok": True}


def test_serialize_output_raises_for_unsupported_value() -> None:
    with pytest.raises(ValidationError):
        serialize_output(object())


def test_serialize_output_fallback_dunder_dict_failure_raises() -> None:
    class BadOutput:
        def __init__(self) -> None:
            self.bad = object()

    with pytest.raises(ValidationError):
        serialize_output(BadOutput())


def test_serialize_output_streamed_passthrough_branch() -> None:
    from pyferox.core.results import Streamed

    streamed = Streamed(chunks=iter(["x"]))
    assert serialize_output(streamed) is streamed


def test_typed_schema_dump_without_output_type_branch() -> None:
    schema = TypedSchema(PlainModel)
    assert schema.dump({"value": 1}) == {"value": 1}


def test_parse_input_dataclass_not_using_kwargs_fallback() -> None:
    @dataclass(slots=True)
    class Input:
        value: int

    with pytest.raises(ValidationError):
        parse_input(Input, {"value": "bad"})


def test_parse_input_struct_not_using_kwargs_fallback() -> None:
    class Input(msgspec.Struct):
        value: int

    with pytest.raises(ValidationError):
        parse_input(Input, {"value": "bad"})


def test_parse_input_builtin_not_using_kwargs_fallback() -> None:
    with pytest.raises(ValidationError):
        parse_input(int, {"value": 1})


def test_parse_input_type_error_fallback_return_branch(monkeypatch) -> None:
    monkeypatch.setattr(schema_runtime.msgspec, "convert", lambda payload, type, strict=False: (_ for _ in ()).throw(TypeError("boom")))
    monkeypatch.setattr(schema_runtime, "_try_construct_from_kwargs", lambda schema_type, payload: PlainModel(value=9))
    parsed = schema_runtime.parse_input(PlainModel, {"value": 1})
    assert parsed.value == 9


def test_details_from_msgspec_error_missing_and_unknown() -> None:
    missing = schema_runtime._details_from_msgspec_error(msgspec.ValidationError("Object missing required field `x`"))
    unknown = schema_runtime._details_from_msgspec_error(msgspec.ValidationError("Object contains unknown field `y`"))
    assert missing == {"x": "Field is required"}
    assert unknown == {"y": "Unexpected field"}


def test_format_validation_error_without_details_branch() -> None:
    payload = schema_runtime.format_validation_error(ValidationError("bad"))
    assert payload == {"type": "validation_error", "error": "bad"}


def test_parse_input_for_plain_command_contract() -> None:
    class CreateUser(Command):
        email: str
        age: int = 18

    parsed = parse_input(CreateUser, {"email": "a@example.com"})
    assert isinstance(parsed, CreateUser)
    assert parsed.email == "a@example.com"
    assert parsed.age == 18

    with pytest.raises(ValidationError):
        parse_input(CreateUser, {"email": "a@example.com", "unknown": True})


def test_contract_metadata_helpers() -> None:
    @contract(audience="internal", version=1)
    class GetUser(Query):
        user_id: int

    parsed = parse_input(GetUser, {"user_id": "7"})
    metadata = get_contract_metadata(parsed)
    assert metadata["audience"] == "internal"
    assert metadata["version"] == 1


def test_schema_metadata_decorator_and_getter() -> None:
    @schema_metadata(title="Create User", description="Create user payload")
    class CreateUser(msgspec.Struct):
        email: str

    metadata = get_schema_metadata(CreateUser)
    assert metadata["title"] == "Create User"
    assert metadata["description"] == "Create user payload"


def test_parse_input_runs_instance_and_class_validators() -> None:
    class Input(msgspec.Struct):
        value: int

        def __validate__(self) -> dict[str, str] | None:
            if self.value < 0:
                return {"value": "Must be non-negative"}
            return None

    with pytest.raises(ValidationError) as exc:
        parse_input(Input, {"value": -1})
    assert exc.value.details["value"] == "Must be non-negative"

    class ClassValidated(msgspec.Struct):
        value: int

        @classmethod
        def validate_payload(cls, payload: "ClassValidated") -> dict[str, str] | None:
            if payload.value > 10:
                return {"value": "Too large"}
            return None

    with pytest.raises(ValidationError) as exc2:
        parse_input(ClassValidated, {"value": 11})
    assert exc2.value.details["value"] == "Too large"
