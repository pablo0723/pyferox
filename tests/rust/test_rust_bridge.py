from pyferox.rust_bridge import (
    compile_schema,
    compile_schema_with_rules,
    compiled_schema_cache_size,
    parse_path_params,
    rust_validation_mode,
    serialize_json,
    validate_compiled,
    validate_compiled_async,
    validate_partial_compiled,
    validate_partial_compiled_async,
    validate_query_compiled,
    validate_query_compiled_async,
)


def test_rust_mode_and_cache():
    assert rust_validation_mode() == "rust-compiled"
    before = compiled_schema_cache_size()
    compile_schema({"a": "int"})
    after = compiled_schema_cache_size()
    assert after >= before


def test_compile_and_validate_full_and_partial():
    compiled = compile_schema({"name": "str", "age": "int"})
    assert validate_compiled(compiled, {"name": "Ada", "age": 3}) == {"name": "Ada", "age": 3}
    assert validate_partial_compiled(compiled, {"age": 5}) == {"age": 5}


def test_compile_with_rules_enforces_constraints_in_rust():
    compiled = compile_schema_with_rules(
        {"name": "str", "age": "int"},
        {
            "name": {"min_length": 2, "allow_blank": False, "choices": ["Ada", "Bob"]},
            "age": {"min_value": 18, "max_value": 65},
        },
    )
    assert validate_partial_compiled(compiled, {"name": "Ada", "age": 33}) == {"name": "Ada", "age": 33}
    import pytest

    with pytest.raises(ValueError):
        validate_partial_compiled(compiled, {"name": "", "age": 33})
    with pytest.raises(ValueError):
        validate_partial_compiled(compiled, {"name": "A", "age": 33})
    with pytest.raises(ValueError):
        validate_partial_compiled(compiled, {"name": "Zed", "age": 33})
    with pytest.raises(ValueError):
        validate_partial_compiled(compiled, {"name": "Ada", "age": 10})


def test_compile_with_rules_regex_and_format():
    import pytest

    compiled = compile_schema_with_rules(
        {"email": "str", "slug": "str", "uid": "str", "born": "str", "site": "str"},
        {
            "email": {"format": "email"},
            "slug": {"regex": r"^[a-z0-9-]+$"},
            "uid": {"format": "uuid"},
            "born": {"format": "date"},
            "site": {"format": "url"},
        },
    )

    ok = validate_partial_compiled(
        compiled,
        {
            "email": "a@example.com",
            "slug": "abc-12",
            "uid": "123e4567-e89b-12d3-a456-426614174000",
            "born": "2026-03-14",
            "site": "https://example.com",
        },
    )
    assert ok["slug"] == "abc-12"

    with pytest.raises(ValueError):
        validate_partial_compiled(compiled, {"email": "bad"})
    with pytest.raises(ValueError):
        validate_partial_compiled(compiled, {"slug": "BAD"})


def test_compile_with_rules_decimal_constraints():
    import pytest

    compiled = compile_schema_with_rules(
        {"amount": "str"},
        {
            "amount": {
                "format": "decimal",
                "max_digits": 6,
                "decimal_places": 2,
                "min_value_decimal": "1.00",
                "max_value_decimal": "9999.99",
            }
        },
    )

    assert validate_partial_compiled(compiled, {"amount": "1234.56"}) == {"amount": "1234.56"}

    with pytest.raises(ValueError):
        validate_partial_compiled(compiled, {"amount": "bad"})
    with pytest.raises(ValueError):
        validate_partial_compiled(compiled, {"amount": "12345.67"})
    with pytest.raises(ValueError):
        validate_partial_compiled(compiled, {"amount": "12.345"})
    with pytest.raises(ValueError):
        validate_partial_compiled(compiled, {"amount": "0.99"})


def test_validate_query_compiled():
    compiled = compile_schema({"active": "bool", "page": "int"})
    out = validate_query_compiled(compiled, {"active": "true", "page": "2"})
    assert out == {"active": True, "page": 2}


def test_validate_query_compiled_json_collection_types():
    compiled = compile_schema({"ids": "list", "meta": "dict"})
    out = validate_query_compiled(compiled, {"ids": "[1,2,3]", "meta": "{\"x\":1}"})
    assert out == {"ids": [1, 2, 3], "meta": {"x": 1}}


def test_parse_path_params():
    assert parse_path_params("/users/{id}", "/users/1") == {"id": "1"}
    assert parse_path_params("/users/{id}", "/posts/1") is None


def test_serialize_json():
    assert serialize_json({"a": 1, "b": [1, 2]}) == '{"a":1,"b":[1,2]}'


def test_async_rust_bridge_functions():
    import asyncio

    compiled = compile_schema({"active": "bool", "page": "int"})

    async def run():
        out1 = await validate_compiled_async(compiled, {"active": True, "page": 1})
        out2 = await validate_partial_compiled_async(compiled, {"page": 2})
        out3 = await validate_query_compiled_async(compiled, {"active": "false", "page": "3"})
        return out1, out2, out3

    v1, v2, v3 = asyncio.run(run())
    assert v1 == {"active": True, "page": 1}
    assert v2 == {"page": 2}
    assert v3 == {"active": False, "page": 3}
