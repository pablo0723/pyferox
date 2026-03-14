from __future__ import annotations

from dataclasses import asdict, is_dataclass

from .errors import HTTPError
from .rust_bridge import compile_schema, validate_partial_compiled, validate_query_compiled
from .schema import _type_to_name

MISSING = object()


class ValidationError(Exception):
    def __init__(self, detail):
        super().__init__("validation error")
        self.detail = detail


class Field:
    def __init__(
        self,
        *,
        required: bool | None = None,
        default=MISSING,
        allow_null: bool = False,
        read_only: bool = False,
        write_only: bool = False,
        alias: str | None = None,
        source: str | None = None,
    ):
        self.required = required
        self.default = default
        self.allow_null = allow_null
        self.read_only = read_only
        self.write_only = write_only
        self.alias = alias
        self.source = source


class Nested(Field):
    def __init__(self, serializer, *, many: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.serializer = serializer
        self.many = many


class Serializer:
    class Meta:
        fields = "__all__"

    def __init__(self, instance=None, data=None, many: bool = False, partial: bool = False):
        self.instance = instance
        self.initial_data = data
        self.many = many
        self.partial = partial
        self._validated_data = None
        self._errors = None

    @property
    def validated_data(self):
        return self._validated_data or ({} if not self.many else [])

    @property
    def errors(self):
        return self._errors or {}

    @property
    def data(self):
        if self.instance is not None:
            if self.many:
                return [self.to_representation(item) for item in self.instance]
            return self.to_representation(self.instance)
        if self._validated_data is not None:
            return self._validated_data
        return {} if not self.many else []

    def is_valid(self, *, raise_exception: bool = False) -> bool:
        try:
            if self.initial_data is None:
                raise ValidationError({"non_field_errors": ["no input data provided"]})
            if self.many:
                if not isinstance(self.initial_data, list):
                    raise ValidationError({"non_field_errors": ["expected list"]})
                self._validated_data = [self.to_internal_value(item) for item in self.initial_data]
            else:
                if not isinstance(self.initial_data, dict):
                    raise ValidationError({"non_field_errors": ["expected object"]})
                self._validated_data = self.to_internal_value(self.initial_data)
            self._errors = {}
            return True
        except ValidationError as exc:
            self._errors = exc.detail
            if raise_exception:
                raise HTTPError(422, "validation failed", exc.detail) from exc
            return False

    def save(self):
        if self._validated_data is None:
            raise RuntimeError("Call is_valid() before save()")
        if self.instance is not None:
            self.instance = self.update(self.instance, self._validated_data)
        else:
            self.instance = self.create(self._validated_data)
        return self.instance

    def create(self, validated_data):
        return validated_data

    def update(self, instance, validated_data):
        if isinstance(instance, dict):
            instance.update(validated_data)
            return instance
        for key, value in validated_data.items():
            setattr(instance, key, value)
        return instance

    @classmethod
    def _type_spec(cls) -> dict[str, str]:
        cached = getattr(cls, "__type_spec_cache__", None)
        if cached is not None:
            return cached
        annotations = getattr(cls, "__annotations__", {})
        out = {}
        for name, tp in annotations.items():
            class_attr = cls.__dict__.get(name, MISSING)
            if isinstance(class_attr, Nested):
                continue
            out[name] = _type_to_name(tp)
        setattr(cls, "__type_spec_cache__", out)
        return out

    @classmethod
    def _field_options(cls) -> dict[str, Field]:
        cached = getattr(cls, "__field_options_cache__", None)
        if cached is not None:
            return cached
        annotations = getattr(cls, "__annotations__", {})
        out = {}
        for name in annotations:
            class_attr = cls.__dict__.get(name, MISSING)
            if isinstance(class_attr, Field):
                out[name] = class_attr
            else:
                out[name] = Field()
        setattr(cls, "__field_options_cache__", out)
        return out

    @classmethod
    def _compiled_type_spec(cls):
        cached = getattr(cls, "__compiled_type_spec_cache__", None)
        if cached is not None:
            return cached
        compiled = compile_schema(cls._type_spec())
        setattr(cls, "__compiled_type_spec_cache__", compiled)
        return compiled

    def to_internal_value(self, data: dict):
        schema = self._type_spec()
        options = self._field_options()
        if not schema and not options:
            return data
        rust_input = {}
        out = {}
        errors = {}
        known_fields = set(options.keys())
        known_aliases = {opt.alias for opt in options.values() if opt.alias}
        for extra in data.keys():
            if extra in known_fields or extra in known_aliases:
                continue
            errors[extra] = ["unknown field"]
        for field_name, field_opt in options.items():
            field_opt = options[field_name]
            if field_opt.read_only:
                continue
            input_key = _input_key(field_name, field_opt)
            source_key = field_opt.source or field_name
            is_nested = isinstance(field_opt, Nested)

            if input_key in data:
                value = data[input_key]
                if value is None:
                    if field_opt.allow_null:
                        out[source_key] = None
                    else:
                        errors[field_name] = ["null is not allowed"]
                    continue
                if is_nested:
                    nested_serializer = field_opt.serializer(data=value, many=field_opt.many, partial=self.partial)
                    if not nested_serializer.is_valid():
                        errors[field_name] = nested_serializer.errors
                    else:
                        out[source_key] = nested_serializer.validated_data
                else:
                    rust_input[field_name] = value
                continue

            if field_opt.default is not MISSING:
                out[source_key] = field_opt.default() if callable(field_opt.default) else field_opt.default
                continue

            required = field_opt.required
            if required is None:
                required = True
            if required and not self.partial:
                errors[field_name] = ["this field is required"]
        if errors:
            raise ValidationError(errors)
        try:
            validated = validate_partial_compiled(self.__class__._compiled_type_spec(), rust_input)
            for field_name, value in validated.items():
                field_opt = options.get(field_name, Field())
                out[field_opt.source or field_name] = value
            return out
        except ValueError as exc:
            raise ValidationError({"reason": str(exc)}) from exc

    @classmethod
    def parse_query_params(cls, query_params: dict[str, str]):
        schema = cls._type_spec()
        if not schema:
            return dict(query_params)
        options = cls._field_options()
        out = {}
        rust_input = {}
        for field_name in schema:
            field_opt = options[field_name]
            input_key = _input_key(field_name, field_opt)
            if input_key not in query_params:
                if field_opt.default is not MISSING:
                    out[field_opt.source or field_name] = (
                        field_opt.default() if callable(field_opt.default) else field_opt.default
                    )
                    continue
                required = field_opt.required
                if required is None:
                    required = True
                if required:
                    raise HTTPError(422, "validation failed", {"reason": f"missing query param: {field_name}"})
                continue
            raw = query_params[input_key]
            if raw.strip().lower() in {"null", "none"}:
                if field_opt.allow_null:
                    out[field_opt.source or field_name] = None
                    continue
                raise HTTPError(422, "validation failed", {"reason": f"null is not allowed for: {field_name}"})
            rust_input[field_name] = raw
        try:
            validated = validate_query_compiled(cls._compiled_type_spec(), rust_input)
            for field_name, value in validated.items():
                field_opt = options.get(field_name, Field())
                out[field_opt.source or field_name] = value
            return out
        except ValueError as exc:
            raise HTTPError(422, "validation failed", {"reason": str(exc)}) from exc

    def to_representation(self, instance):
        field_names = self._field_names()
        options = self._field_options()
        source = _instance_to_dict(instance)
        if field_names == "__all__":
            field_names = list(options.keys())
        out = {}
        for name in field_names:
            opt = options.get(name, Field())
            if opt.write_only:
                continue
            source_key = opt.source or name
            value = _extract_value(source, source_key)
            if isinstance(opt, Nested):
                nested = opt.serializer(instance=value, many=opt.many)
                value = nested.data
            out[opt.alias or name] = value
        return out

    async def ais_valid(self, *, raise_exception: bool = False) -> bool:
        return self.is_valid(raise_exception=raise_exception)

    @classmethod
    def _field_names(cls):
        meta = getattr(cls, "Meta", None)
        fields = getattr(meta, "fields", "__all__")
        if fields == "__all__":
            annotations = getattr(cls, "__annotations__", {})
            if annotations:
                return list(annotations.keys())
            return "__all__"
        if not isinstance(fields, (list, tuple)):
            raise TypeError("Meta.fields must be '__all__' or list/tuple")
        return list(fields)


class ModelSerializer(Serializer):
    @classmethod
    def _model_class(cls):
        meta = getattr(cls, "Meta", None)
        model = getattr(meta, "model", None)
        if model is None:
            raise TypeError("ModelSerializer requires Meta.model")
        return model

    @classmethod
    def _type_spec(cls) -> dict[str, str]:
        explicit_annotations = getattr(cls, "__annotations__", {})
        if explicit_annotations:
            return super()._type_spec()
        cached = getattr(cls, "__model_type_spec_cache__", None)
        if cached is not None:
            return cached
        model = cls._model_class()
        model_types = _extract_model_types(model)
        field_names = cls._field_names()
        if field_names == "__all__":
            out = {name: _type_to_name(tp) for name, tp in model_types.items()}
            setattr(cls, "__model_type_spec_cache__", out)
            return out
        out = {}
        for name in field_names:
            if name not in model_types:
                raise TypeError(f"Field '{name}' is not present on model {model.__name__}")
            out[name] = _type_to_name(model_types[name])
        setattr(cls, "__model_type_spec_cache__", out)
        return out

    @classmethod
    def _field_options(cls) -> dict[str, Field]:
        cached = getattr(cls, "__field_options_cache__", None)
        if cached is not None:
            return cached
        spec = cls._type_spec()
        out = {}
        for name in spec:
            class_attr = cls.__dict__.get(name, MISSING)
            if isinstance(class_attr, Field):
                out[name] = class_attr
            else:
                out[name] = Field()
        setattr(cls, "__field_options_cache__", out)
        return out

    def create(self, validated_data):
        model = self._model_class()
        return model(**validated_data)


def _instance_to_dict(instance):
    if isinstance(instance, dict):
        return dict(instance)
    if is_dataclass(instance):
        return asdict(instance)
    if hasattr(instance, "__dict__"):
        return {k: v for k, v in vars(instance).items() if not k.startswith("_")}
    return {}


def _input_key(field_name: str, field_opt: Field):
    return field_opt.alias or field_name


def _extract_value(source: dict, source_key: str):
    if "." not in source_key:
        return source.get(source_key)
    value = source
    for part in source_key.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            value = getattr(value, part, None)
        if value is None:
            break
    return value


def _extract_model_types(model) -> dict[str, type]:
    annotations = getattr(model, "__annotations__", {})
    if annotations:
        return dict(annotations)
    meta = getattr(model, "_meta", None)
    if meta is None or not hasattr(meta, "get_fields"):
        raise TypeError(
            f"Cannot infer field types for model {model!r}. "
            "Add model annotations or serializer field annotations."
        )
    out = {}
    for field in meta.get_fields():
        name = getattr(field, "name", None)
        if not name:
            continue
        internal_type = field.get_internal_type()
        py_type = _django_type_to_python(internal_type)
        if py_type is None:
            continue
        out[name] = py_type
    return out


def _django_type_to_python(internal_type: str):
    mapping = {
        "CharField": str,
        "TextField": str,
        "SlugField": str,
        "EmailField": str,
        "UUIDField": str,
        "IntegerField": int,
        "BigIntegerField": int,
        "SmallIntegerField": int,
        "AutoField": int,
        "BigAutoField": int,
        "FloatField": float,
        "DecimalField": float,
        "BooleanField": bool,
        "NullBooleanField": bool,
    }
    return mapping.get(internal_type)
