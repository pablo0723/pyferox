# PyFerOx

Async-first, Rust-accelerated API layer for Django projects.

## Project status

PyFerOx is a hobby framework maintained by one person with AI assistance.
Support is best-effort (no SLA).

## Architecture

PyFerOx is now Django-first:

- Django handles routing, admin, auth/session middleware, ORM, and ecosystem features.
- PyFerOx provides fast serializer/query validation and API ergonomics.
- Rust core (`pyferox-rust`) accelerates validation, query coercion, path parsing, and JSON serialization.

## Install

```bash
pip install pyferox
```

For local dev before publishing `pyferox-rust` to PyPI:

```bash
python -m maturin build --manifest-path rust-core/Cargo.toml
pip install . --find-links rust-core/target/wheels
```

## Clean imports

```python
from pyferox import (
    API,
    Schema,
    Serializer,
    ModelSerializer,
    Field,
    StringField,
    IntegerField,
    BooleanField,
    EmailField,
    URLField,
    UUIDField,
    DateField,
    DateTimeField,
    TimeField,
    DecimalField,
    ListField,
    DictField,
    Nested,
    HTTPError,
)
```

`API` is alias of `DjangoAPI`.

## Quickstart (Django)

```python
# urls.py
from django.contrib import admin
from django.urls import include, path
from pyferox import API, Field, Serializer


class CreateUserIn(Serializer):
    name: str
    age: int = Field(required=False, default=18)


class UserOut(Serializer):
    id: int
    name: str
    age: int


api = API(prefix="api")


@api.post("users", input_schema=CreateUserIn, output_schema=UserOut)
async def create_user(request):
    payload = request.data
    return {"id": 1, **payload}


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include(api.urls)),
]
```

## Serializer features

- `Field(required=..., default=..., allow_null=..., read_only=..., write_only=...)`
- `Field(alias="...", source="...")`
- `Nested(OtherSerializer, many=False|True)`
- Specialized fields:
  `StringField`, `IntegerField`, `FloatField`, `BooleanField`,
  `EmailField`, `URLField`, `UUIDField`,
  `DateField`, `DateTimeField`, `TimeField`, `DecimalField`,
  `ListField(child=...)`, `DictField(value_field=...)`
- Typing support for annotations: `Optional[T]`, `list[T]`, `dict[K, V]`
- `partial=True` update mode
- Rust-accelerated typed query parsing (including JSON list/dict query values)
- Rust-compiled field constraints for hot-path validation: `choices`, `allow_blank`, `min/max_length`, `min/max_value`, `regex`, and format checks (`email/url/uuid/date/datetime/time`)
- Async validation path via `Serializer.ais_valid()` / `Serializer.aparse_query_params()`

## Legacy ASGI adapter

If you still need to wrap an ASGI-style PyFerOx app:

```python
from pyferox.django import as_django_view
```

## Tests

```bash
pip install -e ".[dev]" --find-links rust-core/target/wheels
pytest
```

Test layout is split by module:

- `tests/core/` - errors/request/response/schema/serializers/export tests
- `tests/django/` - `DjangoAPI` + adapter integration tests
- `tests/rust/` - rust bridge and compiled-schema runtime tests
