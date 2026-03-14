# PyFerOx (v0.1)

Minimal DRF-style API framework with async-capable runtime and Rust-accelerated core.

## Project status

PyFerOx is a hobby framework maintained by one person with AI assistance.

Support policy:

- no SLA
- best-effort maintenance
- API and internals may change between minor versions
- community support is limited

Use it when you want to move fast and can tolerate rapid iteration.

## Install

```bash
pip install pyferox
```

`pyferox` requires `pyferox-rust` at runtime. For local development before publishing `pyferox-rust` to PyPI:

```bash
python -m maturin build --manifest-path rust-core/Cargo.toml
pip install . --find-links rust-core/target/wheels
```

## Quickstart

Create `app.py`:

```python
from pyferox import API, HTTPError, Schema
from pyferox.response import JSONResponse


class CreateUserIn(Schema):
    name: str
    age: int


class CreateUserOut(Schema):
    id: int
    name: str
    age: int


app = API()


@app.post("/users", input_schema=CreateUserIn, output_schema=CreateUserOut)
async def create_user(request):
    payload = request.json_body
    if payload["age"] < 0:
        raise HTTPError(422, "age must be >= 0")
    return {"id": 1, **payload}


@app.get("/users/{user_id}")
def get_user(request):
    if request.path_params["user_id"] != "1":
        raise HTTPError(404, "user not found")
    return JSONResponse({"id": 1, "name": "Ada", "age": 33})
```

Run with ASGI server:

```bash
pip install uvicorn
uvicorn app:app --reload
```

Test endpoint:

```bash
curl -X POST http://127.0.0.1:8000/users \
  -H "content-type: application/json" \
  -d '{"name":"Ada","age":33}'
```

## Core concepts

- `API`: router + ASGI app entry point.
- `APIView`: DRF-style class-based views.
- `Schema`: input/output validation contract.
- `Serializer` / `ModelSerializer`: DRF-like typed contracts for migration-friendly code.
- `@app.get`, `@app.post`: route decorators.
- `Request`: has `method`, `path`, `headers`, `query_params`, `query_data`, `path_params`, `json_body`.
- `Response` / `JSONResponse`: explicit response control.
- `HTTPError(status, message, details=None)`: controlled application errors.

## Validation and errors

Supported schema field types in v0.1:

- `str`
- `int`
- `float`
- `bool`

Error response format:

```json
{
  "error": {
    "code": 422,
    "message": "validation failed",
    "details": {
      "reason": "missing field: age"
    }
  }
}
```

Default behavior:

- Unknown route -> `404`
- Invalid JSON body -> `400`
- Schema validation failure -> `422`
- Unhandled exception -> `500`

## DRF-style migration example

You can pass serializer classes directly into route decorators and keep DRF-like structure:

```python
from pyferox import API, Serializer, ModelSerializer


class CreateUserSerializer(Serializer):
    name: str
    age: int


class UserSerializer(ModelSerializer):
    class Meta:
        model = User  # dataclass or Django model
        fields = ["id", "name", "age"]


app = API()


@app.post("/users", input_schema=CreateUserSerializer, output_schema=UserSerializer)
def create_user(request):
    payload = request.data  # DRF-like alias
    user = User(id=1, name=payload["name"], age=payload["age"])
    return user
```

Current migration-friendly features:

- `request.data` alias
- `request.query_data` alias for typed parsed query params
- `Serializer(data=...).is_valid()`
- `serializer.validated_data`, `serializer.errors`, `serializer.data`
- `ModelSerializer` with `Meta.model` and `Meta.fields`
- DRF-like field options: `Field(required=..., default=..., allow_null=..., read_only=..., write_only=...)`
- field mapping options: `Field(alias="...", source="...")`
- nested serializers: `Nested(OtherSerializer, many=False|True)`
- class-based views via `APIView`
- permissions (`BasePermission`, `AllowAny`, `IsAuthenticated`)
- pagination (`PageNumberPagination`)
- query parsing via `query_schema=` on routes or `query_serializer_class` on APIView
- `ViewSet` + `ResourceRouter` for DRF-like resource routes
- filter backends (`FieldFilterBackend`, `SearchFilter`, `OrderingFilter`)
- authentication hooks (`authentication_classes`, `TokenAuthentication`)
- OpenAPI generation via `app.openapi()`

Example:

```python
from pyferox import (
    API,
    ResourceRouter,
    Serializer,
    ViewSet,
    IsAuthenticated,
    TokenAuthentication,
    FieldFilterBackend,
    SearchFilter,
    OrderingFilter,
)


class ProductSerializer(Serializer):
    id: int
    name: str
    category: str


class ProductViewSet(ViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]
    filter_backends = [FieldFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["category"]
    search_fields = ["name"]
    ordering_fields = ["id", "name"]

    def get_queryset(self):
        return [{"id": 1, "name": "Apple", "category": "fruit"}]

    def list(self, request):
        return self.get_queryset()

    def retrieve(self, request):
        return self.get_object()


app = API()
router = ResourceRouter()
router.register("products", ProductViewSet, basename="products")
app.include_router(router)

openapi_schema = app.openapi(title="My API", version="0.3.0")
```

## v0.4 features

- Rust-first serializer/validator runtime path
- compiled schema cache for repeated validations
- async-capable hooks for auth/permissions/filters/pagination

How it works:

- `Schema` and `Serializer` compile type specs once and reuse compiled validators.
- `pyferox_rust` now provides `compile_schema` + `validate_compiled`.
- Query param typed coercion is handled in Rust via compiled schemas.
- JSON serialization and path matching are Rust-accelerated by default.
- `authentication_classes`, `permission_classes`, `filter_backends`, and pagination hooks support both sync and `async def`.
- `query_schema` contract in routes supports sync or async `validate_query(...)`.

Example with class-based view, permissions, query parsing and pagination:

```python
from pyferox import API, APIView, IsAuthenticated, PageNumberPagination, Serializer


class ItemsQuery(Serializer):
    page: int
    page_size: int


class ItemsPagination(PageNumberPagination):
    page_size = 20
    max_page_size = 100


class ItemsView(APIView):
    permission_classes = [IsAuthenticated]
    query_serializer_class = ItemsQuery
    pagination_class = ItemsPagination

    def get(self, request):
        page = request.query_data["page"]
        page_size = request.query_data["page_size"]
        items = [{"id": i} for i in range(1, 501)]
        return items


app = API()
app.add_api_view("/items", ItemsView)
```

## v0.4 scope

- `API`
- `APIView`
- `ViewSet` + `ResourceRouter`
- `Schema`
- `Serializer` / `ModelSerializer`
- `@get` / `@post` / `@put` / `@patch` / `@delete`
- `Request` / `Response`
- JSON body parsing
- input validation
- output serialization
- basic error handling
- permissions
- page-number pagination
- typed query parsing
- filter backends
- authentication hooks
- OpenAPI generation
- Rust-first compiled schema validation path

Not included yet:

- full authentication framework (token/session/jwt providers, refresh flows)
- ORM integration
- advanced schema types (nested models, unions, custom validators)

## Local development

```bash
python3 -m unittest tests/test_smoke.py
```

## Local build: Rust core

Requirements: Rust toolchain + `maturin`.

```bash
pip install maturin
python -m maturin build --manifest-path rust-core/Cargo.toml
pip install --force-reinstall rust-core/target/wheels/pyferox_rust-*.whl
python3 -m unittest tests/test_smoke.py
```

## Project layout

- `pyferox/` - Python framework surface (routing, request/response, schema, errors)
- `rust-core/` - `pyo3` extension module (`pyferox_rust`) published as `pyferox-rust`
- `tests/test_smoke.py` - basic end-to-end smoke tests
- `main.py` - tiny usage example

## Publish to PyPI

Main package (`pyferox`):

```bash
pip install build twine
python -m build
python -m twine upload dist/*
```

Rust package (`pyferox-rust`):

```bash
cd rust-core
pip install maturin twine
python -m maturin build --release
python -m twine upload target/wheels/*
```
