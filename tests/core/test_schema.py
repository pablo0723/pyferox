import pytest

from pyferox.errors import HTTPError
from pyferox.schema import Schema, _type_to_name


class UserSchema(Schema):
    name: str
    age: int
    active: bool


def test_type_to_name_supported():
    assert _type_to_name(str) == "str"
    assert _type_to_name(int) == "int"
    assert _type_to_name(float) == "float"
    assert _type_to_name(bool) == "bool"
    assert _type_to_name(list[int]) == "list"
    assert _type_to_name(dict[str, int]) == "dict"
    assert _type_to_name(str | None) == "str"


def test_type_to_name_unsupported():
    with pytest.raises(TypeError):
        _type_to_name(tuple)


def test_schema_validate_success():
    out = UserSchema.validate({"name": "Ada", "age": 33, "active": True})
    assert out == {"name": "Ada", "age": 33, "active": True}


def test_schema_validate_rust_error_to_http_error():
    with pytest.raises(HTTPError) as exc:
        UserSchema.validate({"name": "Ada", "age": "bad", "active": True})
    assert exc.value.status_code == 422


def test_schema_validate_wrong_payload_shape():
    with pytest.raises(HTTPError) as exc:
        UserSchema.validate(["bad"])
    assert exc.value.status_code == 422


def test_schema_validate_query():
    out = UserSchema.validate_query({"name": "Ada", "age": "33", "active": "true"})
    assert out == {"name": "Ada", "age": 33, "active": True}


def test_schema_validate_query_missing():
    with pytest.raises(HTTPError) as exc:
        UserSchema.validate_query({"name": "Ada", "age": "33"})
    assert exc.value.status_code == 422


def test_schema_validate_query_rust_error():
    with pytest.raises(HTTPError) as exc:
        UserSchema.validate_query({"name": "Ada", "age": "bad", "active": "true"})
    assert exc.value.status_code == 422
