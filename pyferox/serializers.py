from __future__ import annotations

import asyncio
import datetime as dt
import re
from decimal import Decimal, InvalidOperation
from dataclasses import asdict, is_dataclass
from typing import get_args, get_origin
from urllib.parse import urlparse
from uuid import UUID

from .errors import HTTPError
from .rust_bridge import (
    compile_schema,
    compile_schema_with_rules,
    validate_partial_compiled,
    validate_partial_compiled_async,
    validate_query_compiled,
    validate_query_compiled_async,
)
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
        choices=None,
        allow_blank: bool = True,
        min_length: int | None = None,
        max_length: int | None = None,
        min_value: float | int | None = None,
        max_value: float | int | None = None,
        regex: str | re.Pattern | None = None,
        validators: list | None = None,
        rust_type: str | None = None,
    ):
        self.required = required
        self.default = default
        self.allow_null = allow_null
        self.read_only = read_only
        self.write_only = write_only
        self.alias = alias
        self.source = source
        self.choices = choices
        self.allow_blank = allow_blank
        self.min_length = min_length
        self.max_length = max_length
        self.min_value = min_value
        self.max_value = max_value
        self.regex = re.compile(regex) if isinstance(regex, str) else regex
        self.validators = validators or []
        self.rust_type = rust_type

    def run_validation(self, field_name: str, value):
        if value is None:
            return value
        if self.choices is not None and value not in self.choices:
            raise ValueError(f"invalid choice for {field_name}")
        if isinstance(value, str):
            if not self.allow_blank and value == "":
                raise ValueError(f"blank is not allowed for {field_name}")
            if self.min_length is not None and len(value) < self.min_length:
                raise ValueError(f"min_length violation for {field_name}")
            if self.max_length is not None and len(value) > self.max_length:
                raise ValueError(f"max_length violation for {field_name}")
            if self.regex is not None and self.regex.fullmatch(value) is None:
                raise ValueError(f"regex violation for {field_name}")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if self.min_value is not None and value < self.min_value:
                raise ValueError(f"min_value violation for {field_name}")
            if self.max_value is not None and value > self.max_value:
                raise ValueError(f"max_value violation for {field_name}")
        for validator in self.validators:
            validator(value)
        return value


class StringField(Field):
    def __init__(self, **kwargs):
        super().__init__(rust_type="str", **kwargs)


class IntegerField(Field):
    def __init__(self, **kwargs):
        super().__init__(rust_type="int", **kwargs)


class FloatField(Field):
    def __init__(self, **kwargs):
        super().__init__(rust_type="float", **kwargs)


class BooleanField(Field):
    def __init__(self, **kwargs):
        super().__init__(rust_type="bool", **kwargs)


class UUIDField(StringField):
    def run_validation(self, field_name: str, value):
        value = super().run_validation(field_name, value)
        try:
            UUID(str(value))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid uuid for {field_name}") from exc
        return str(value)


class EmailField(StringField):
    _EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    def run_validation(self, field_name: str, value):
        value = super().run_validation(field_name, value)
        if self._EMAIL_RE.fullmatch(value) is None:
            raise ValueError(f"invalid email for {field_name}")
        return value


class URLField(StringField):
    def run_validation(self, field_name: str, value):
        value = super().run_validation(field_name, value)
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"invalid url for {field_name}")
        return value


class DateField(StringField):
    def run_validation(self, field_name: str, value):
        value = super().run_validation(field_name, value)
        try:
            dt.date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"invalid date for {field_name}") from exc
        return value


class DateTimeField(StringField):
    def run_validation(self, field_name: str, value):
        value = super().run_validation(field_name, value)
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            dt.datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(f"invalid datetime for {field_name}") from exc
        return value


class TimeField(StringField):
    def run_validation(self, field_name: str, value):
        value = super().run_validation(field_name, value)
        try:
            dt.time.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"invalid time for {field_name}") from exc
        return value


class DecimalField(StringField):
    def __init__(self, *, max_digits: int | None = None, decimal_places: int | None = None, **kwargs):
        super().__init__(**kwargs)
        self.max_digits = max_digits
        self.decimal_places = decimal_places

    def run_validation(self, field_name: str, value):
        value = super().run_validation(field_name, value)
        try:
            dec = Decimal(value)
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError(f"invalid decimal for {field_name}") from exc

        if self.max_value is not None and dec > Decimal(str(self.max_value)):
            raise ValueError(f"max_value violation for {field_name}")
        if self.min_value is not None and dec < Decimal(str(self.min_value)):
            raise ValueError(f"min_value violation for {field_name}")
        if self.max_digits is not None:
            digits = len(dec.as_tuple().digits)
            if digits > self.max_digits:
                raise ValueError(f"max_digits violation for {field_name}")
        if self.decimal_places is not None:
            decimals = -dec.as_tuple().exponent if dec.as_tuple().exponent < 0 else 0
            if decimals > self.decimal_places:
                raise ValueError(f"decimal_places violation for {field_name}")
        return str(value)


class ListField(Field):
    def __init__(self, *, child: Field | None = None, allow_empty: bool = True, **kwargs):
        super().__init__(rust_type="list", **kwargs)
        self.child = child
        self.allow_empty = allow_empty

    def run_validation(self, field_name: str, value):
        value = super().run_validation(field_name, value)
        if not isinstance(value, list):
            raise ValueError(f"expected list for {field_name}")
        if not self.allow_empty and not value:
            raise ValueError(f"empty list is not allowed for {field_name}")
        if self.min_length is not None and len(value) < self.min_length:
            raise ValueError(f"min_length violation for {field_name}")
        if self.max_length is not None and len(value) > self.max_length:
            raise ValueError(f"max_length violation for {field_name}")
        if self.child is not None:
            return [self.child.run_validation(f"{field_name}[]", item) for item in value]
        return value


class DictField(Field):
    def __init__(self, *, value_field: Field | None = None, **kwargs):
        super().__init__(rust_type="dict", **kwargs)
        self.value_field = value_field

    def run_validation(self, field_name: str, value):
        value = super().run_validation(field_name, value)
        if not isinstance(value, dict):
            raise ValueError(f"expected dict for {field_name}")
        if self.value_field is not None:
            out = {}
            for key, item in value.items():
                out[key] = self.value_field.run_validation(f"{field_name}.{key}", item)
            return out
        return value


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

    async def ais_valid(self, *, raise_exception: bool = False) -> bool:
        try:
            if self.initial_data is None:
                raise ValidationError({"non_field_errors": ["no input data provided"]})
            if self.many:
                if not isinstance(self.initial_data, list):
                    raise ValidationError({"non_field_errors": ["expected list"]})
                self._validated_data = await asyncio.gather(
                    *(self.to_internal_value_async(item) for item in self.initial_data)
                )
            else:
                if not isinstance(self.initial_data, dict):
                    raise ValidationError({"non_field_errors": ["expected object"]})
                self._validated_data = await self.to_internal_value_async(self.initial_data)
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
            if isinstance(class_attr, Field) and class_attr.rust_type:
                out[name] = class_attr.rust_type
            else:
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
                _, is_optional = _unwrap_optional_type(annotations[name])
                out[name] = Field(required=not is_optional, allow_null=is_optional)
        setattr(cls, "__field_options_cache__", out)
        return out

    @classmethod
    def _compiled_type_spec(cls):
        cached = getattr(cls, "__compiled_type_spec_cache__", None)
        if cached is not None:
            return cached
        schema = cls._type_spec()
        rules = cls._rust_rules_spec()
        if rules:
            compiled = compile_schema_with_rules(schema, rules)
        else:
            compiled = compile_schema(schema)
        setattr(cls, "__compiled_type_spec_cache__", compiled)
        return compiled

    @classmethod
    def _rust_rules_spec(cls) -> dict[str, dict]:
        options = cls._field_options()
        out = {}
        for field_name, opt in options.items():
            if isinstance(opt, Nested):
                continue
            rules = {}
            if opt.choices is not None:
                rules["choices"] = list(opt.choices)
            if opt.allow_blank is False:
                rules["allow_blank"] = False
            if opt.min_length is not None:
                rules["min_length"] = int(opt.min_length)
            if opt.max_length is not None:
                rules["max_length"] = int(opt.max_length)
            if opt.min_value is not None:
                if isinstance(opt, DecimalField):
                    rules["min_value_decimal"] = str(opt.min_value)
                else:
                    rules["min_value"] = float(opt.min_value)
            if opt.max_value is not None:
                if isinstance(opt, DecimalField):
                    rules["max_value_decimal"] = str(opt.max_value)
                else:
                    rules["max_value"] = float(opt.max_value)
            if isinstance(opt, DecimalField):
                if opt.max_digits is not None:
                    rules["max_digits"] = int(opt.max_digits)
                if opt.decimal_places is not None:
                    rules["decimal_places"] = int(opt.decimal_places)
            if opt.regex is not None:
                rules["regex"] = opt.regex.pattern
            field_format = _field_rust_format(opt)
            if field_format is not None:
                rules["format"] = field_format
            if rules:
                out[field_name] = rules
        return out

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
                    if field_opt.many and not isinstance(value, list):
                        errors[field_name] = ["expected list"]
                        continue
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
                if _needs_python_post_validation(field_opt):
                    normalized = _apply_field_constraints(field_name, value, field_opt)
                else:
                    normalized = value
                out[field_opt.source or field_name] = normalized
            return out
        except ValueError as exc:
            raise ValidationError({"reason": str(exc)}) from exc

    async def to_internal_value_async(self, data: dict):
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
                    if field_opt.many and not isinstance(value, list):
                        errors[field_name] = ["expected list"]
                        continue
                    nested_serializer = field_opt.serializer(data=value, many=field_opt.many, partial=self.partial)
                    if not await nested_serializer.ais_valid():
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
            validated = await validate_partial_compiled_async(self.__class__._compiled_type_spec(), rust_input)
            for field_name, value in validated.items():
                field_opt = options.get(field_name, Field())
                if _needs_python_post_validation(field_opt):
                    normalized = _apply_field_constraints(field_name, value, field_opt)
                else:
                    normalized = value
                out[field_opt.source or field_name] = normalized
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
                if _needs_python_post_validation(field_opt):
                    normalized = _apply_field_constraints(field_name, value, field_opt)
                else:
                    normalized = value
                out[field_opt.source or field_name] = normalized
            return out
        except ValueError as exc:
            raise HTTPError(422, "validation failed", {"reason": str(exc)}) from exc

    @classmethod
    async def aparse_query_params(cls, query_params: dict[str, str]):
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
            validated = await validate_query_compiled_async(cls._compiled_type_spec(), rust_input)
            for field_name, value in validated.items():
                field_opt = options.get(field_name, Field())
                if _needs_python_post_validation(field_opt):
                    normalized = _apply_field_constraints(field_name, value, field_opt)
                else:
                    normalized = value
                out[field_opt.source or field_name] = normalized
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
        model_opts = _extract_model_field_options(cls._model_class())
        out = {}
        for name in spec:
            class_attr = cls.__dict__.get(name, MISSING)
            if isinstance(class_attr, Field):
                out[name] = class_attr
            else:
                out[name] = model_opts.get(name, Field())
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


def _apply_field_constraints(field_name: str, value, field_opt: Field):
    return field_opt.run_validation(field_name, value)


def _needs_python_post_validation(field_opt: Field) -> bool:
    if field_opt.validators:
        return True
    return isinstance(field_opt, (ListField, DictField))


def _field_rust_format(field_opt: Field) -> str | None:
    if isinstance(field_opt, EmailField):
        return "email"
    if isinstance(field_opt, URLField):
        return "url"
    if isinstance(field_opt, UUIDField):
        return "uuid"
    if isinstance(field_opt, DateField):
        return "date"
    if isinstance(field_opt, DateTimeField):
        return "datetime"
    if isinstance(field_opt, TimeField):
        return "time"
    if isinstance(field_opt, DecimalField):
        return "decimal"
    return None


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


def _extract_model_field_options(model) -> dict[str, Field]:
    meta = getattr(model, "_meta", None)
    if meta is None or not hasattr(meta, "get_fields"):
        return {}
    out: dict[str, Field] = {}
    for field in meta.get_fields():
        name = getattr(field, "name", None)
        if not name:
            continue
        if getattr(field, "auto_created", False) and not getattr(field, "concrete", False):
            continue

        required = not bool(getattr(field, "blank", False))
        if getattr(field, "null", False):
            required = False
        default = MISSING
        has_default = getattr(field, "has_default", None)
        if callable(has_default) and has_default():
            default = field.default

        choices_attr = getattr(field, "choices", None)
        choices = None
        if choices_attr:
            choices = [item[0] for item in choices_attr]

        allow_blank = bool(getattr(field, "blank", True))
        min_length = getattr(field, "min_length", None)
        max_length = getattr(field, "max_length", None)
        min_value = getattr(field, "min_value", None)
        max_value = getattr(field, "max_value", None)
        editable = bool(getattr(field, "editable", True))
        read_only = not editable
        allow_null = bool(getattr(field, "null", False))

        validators = []
        for validator in getattr(field, "validators", []):
            if callable(validator):
                validators.append(validator)

        field_cls = _django_field_to_serializer_field(getattr(field, "get_internal_type", lambda: "")())
        out[name] = field_cls(
            required=required,
            default=default,
            allow_null=allow_null,
            read_only=read_only,
            allow_blank=allow_blank,
            min_length=min_length,
            max_length=max_length,
            min_value=min_value,
            max_value=max_value,
            choices=choices,
            validators=validators,
        )
    return out


def _django_type_to_python(internal_type: str):
    mapping = {
        "CharField": str,
        "TextField": str,
        "SlugField": str,
        "EmailField": str,
        "UUIDField": str,
        "URLField": str,
        "DateField": str,
        "DateTimeField": str,
        "TimeField": str,
        "DurationField": str,
        "IntegerField": int,
        "BigIntegerField": int,
        "SmallIntegerField": int,
        "PositiveIntegerField": int,
        "PositiveSmallIntegerField": int,
        "AutoField": int,
        "BigAutoField": int,
        "ForeignKey": int,
        "OneToOneField": int,
        "FloatField": float,
        "DecimalField": float,
        "BooleanField": bool,
        "NullBooleanField": bool,
        "JSONField": dict,
        "ManyToManyField": list,
        "ArrayField": list,
    }
    return mapping.get(internal_type)


def _unwrap_optional_type(field_type):
    origin = get_origin(field_type)
    if origin is None:
        return field_type, False
    args = get_args(field_type)
    non_none = [arg for arg in args if arg is not type(None)]
    if len(non_none) == 1 and len(non_none) != len(args):
        return non_none[0], True
    return field_type, False


def _django_field_to_serializer_field(internal_type: str):
    mapping = {
        "CharField": StringField,
        "TextField": StringField,
        "SlugField": StringField,
        "EmailField": EmailField,
        "UUIDField": UUIDField,
        "URLField": URLField,
        "DateField": DateField,
        "DateTimeField": DateTimeField,
        "TimeField": TimeField,
        "DurationField": StringField,
        "IntegerField": IntegerField,
        "BigIntegerField": IntegerField,
        "SmallIntegerField": IntegerField,
        "PositiveIntegerField": IntegerField,
        "PositiveSmallIntegerField": IntegerField,
        "AutoField": IntegerField,
        "BigAutoField": IntegerField,
        "ForeignKey": IntegerField,
        "OneToOneField": IntegerField,
        "FloatField": FloatField,
        "DecimalField": DecimalField,
        "BooleanField": BooleanField,
        "NullBooleanField": BooleanField,
        "JSONField": DictField,
        "ManyToManyField": ListField,
        "ArrayField": ListField,
    }
    return mapping.get(internal_type, Field)
