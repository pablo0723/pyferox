from dataclasses import dataclass

import pytest

from pyferox import (
    DateField,
    DateTimeField,
    DecimalField,
    DictField,
    EmailField,
    Field,
    ListField,
    ModelSerializer,
    Nested,
    Serializer,
    TimeField,
    URLField,
    UUIDField,
)
from pyferox.errors import HTTPError
from pyferox.serializers import (
    BooleanField,
    FloatField,
    IntegerField,
    StringField,
    ValidationError,
    _django_field_to_serializer_field,
    _django_type_to_python,
    _extract_model_field_options,
    _extract_model_types,
    _extract_value,
    _input_key,
)


class BaseIn(Serializer):
    id: int = Field(read_only=True)
    name: str
    age: int = Field(required=False, default=18)
    nickname: str = Field(required=False, allow_null=True)
    password: str = Field(write_only=True)


class QueryIn(Serializer):
    page: int = Field(required=False, default=1)
    page_size: int = Field(required=False, default=20)
    active: bool


class Constrained(Serializer):
    name: str = Field(min_length=2, max_length=5, regex=r"^[A-Z][a-z]+$", allow_blank=False)
    age: int = Field(min_value=18, max_value=60)
    role: str = Field(choices=["admin", "user"])


class ProfileIn(Serializer):
    city: str


class AliasNested(Serializer):
    display_name: str = Field(alias="displayName", source="name")
    profile: dict = Nested(ProfileIn, source="profile_data")


@dataclass
class UserModel:
    id: int
    name: str
    age: int


class UserModelSerializer(ModelSerializer):
    class Meta:
        model = UserModel
        fields = ["id", "name", "age"]


def test_serializer_valid_and_save_create_update():
    s = BaseIn(data={"name": "Ada", "password": "s"})
    assert s.is_valid()
    assert s.validated_data["age"] == 18
    created = s.save()
    assert created["name"] == "Ada"

    instance = {"name": "X", "age": 1}
    s2 = BaseIn(instance=instance, data={"name": "Y", "password": "s"}, partial=True)
    assert s2.is_valid()
    updated = s2.save()
    assert updated["name"] == "Y"


def test_serializer_errors_and_raise_exception():
    s = BaseIn(data=None)
    assert not s.is_valid()
    assert "non_field_errors" in s.errors
    with pytest.raises(HTTPError):
        BaseIn(data={"age": "bad"}).is_valid(raise_exception=True)


def test_serializer_many_requires_list():
    s = BaseIn(data={"name": "Ada"}, many=True)
    assert not s.is_valid()


def test_serializer_plain_expected_object():
    s = BaseIn(data=["bad"])
    assert not s.is_valid()


def test_serializer_async_validation_paths():
    import asyncio

    async def run_ok():
        s = BaseIn(data={"name": "Ada", "password": "x"})
        assert await s.ais_valid()

    async def run_fail():
        s = BaseIn(data={"age": "bad"})
        ok = await s.ais_valid()
        assert ok is False
        with pytest.raises(HTTPError):
            await BaseIn(data={"age": "bad"}).ais_valid(raise_exception=True)

    asyncio.run(run_ok())
    asyncio.run(run_fail())


def test_serializer_partial_and_unknown_and_null():
    assert BaseIn(data={"age": 21}, partial=True).is_valid()
    s_unknown = BaseIn(data={"name": "Ada", "password": "s", "extra": 1})
    assert not s_unknown.is_valid()
    s_null_bad = BaseIn(data={"name": "Ada", "password": "s", "age": None})
    assert not s_null_bad.is_valid()
    s_null_ok = BaseIn(data={"name": "Ada", "password": "s", "nickname": None})
    assert s_null_ok.is_valid()


def test_serializer_data_and_many():
    one = BaseIn(instance={"id": 1, "name": "Ada", "age": 33, "password": "x"})
    assert "password" not in one.data
    many = BaseIn(instance=[{"id": 1, "name": "Ada", "age": 33, "password": "x"}], many=True)
    assert many.data[0]["name"] == "Ada"


def test_serializer_query_params():
    parsed = QueryIn.parse_query_params({"active": "1"})
    assert parsed == {"page": 1, "page_size": 20, "active": True}
    with pytest.raises(HTTPError):
        QueryIn.parse_query_params({})


def test_serializer_constrained_fields():
    ok = Constrained(data={"name": "Ada", "age": 20, "role": "admin"})
    assert ok.is_valid()

    bad_len = Constrained(data={"name": "A", "age": 20, "role": "admin"})
    assert not bad_len.is_valid()
    bad_regex = Constrained(data={"name": "ADA", "age": 20, "role": "admin"})
    assert not bad_regex.is_valid()
    bad_range = Constrained(data={"name": "Ada", "age": 10, "role": "admin"})
    assert not bad_range.is_valid()
    bad_choice = Constrained(data={"name": "Ada", "age": 20, "role": "super"})
    assert not bad_choice.is_valid()


def test_alias_and_nested_in_out():
    s = AliasNested(data={"displayName": "Ada", "profile": {"city": "Kyiv"}})
    assert s.is_valid()
    assert s.validated_data == {"name": "Ada", "profile_data": {"city": "Kyiv"}}
    out = AliasNested(instance={"name": "Ada", "profile_data": {"city": "Kyiv"}}).data
    assert out == {"displayName": "Ada", "profile": {"city": "Kyiv"}}


def test_nested_many_expected_list_error():
    class Child(Serializer):
        city: str

    class Parent(Serializer):
        profile: list = Nested(Child, many=True)

    s = Parent(data={"profile": {"city": "Kyiv"}})
    assert not s.is_valid()
    assert "profile" in s.errors


def test_ais_valid():
    s = BaseIn(data={"name": "Ada", "password": "x"})
    import asyncio

    assert asyncio.run(s.ais_valid())


def test_aparse_query_params_async():
    import asyncio

    parsed = asyncio.run(QueryIn.aparse_query_params({"active": "true"}))
    assert parsed["active"] is True
    assert parsed["page"] == 1


def test_save_without_validation_raises():
    with pytest.raises(RuntimeError):
        BaseIn(data={"name": "Ada"}).save()


def test_update_non_dict_instance():
    class Obj:
        def __init__(self):
            self.name = "a"

    obj = Obj()
    s = BaseIn(instance=obj, data={"name": "b", "password": "x"}, partial=True)
    assert s.is_valid()
    out = s.save()
    assert out.name == "b"


def test_model_serializer_paths():
    user = UserModel(id=1, name="Ada", age=30)
    out = UserModelSerializer(instance=user).data
    assert out["name"] == "Ada"
    s = UserModelSerializer(data={"id": 2, "name": "Bob", "age": 20})
    assert s.is_valid()
    created = s.save()
    assert isinstance(created, UserModel)
    assert created.id == 2


def test_model_serializer_all_fields_branch():
    class AllFields(ModelSerializer):
        class Meta:
            model = UserModel
            fields = "__all__"

    out = AllFields(instance=UserModel(id=1, name="Ada", age=1)).data
    assert out["id"] == 1


def test_model_serializer_explicit_annotations_branch():
    class ExplicitMS(ModelSerializer):
        id: int

        class Meta:
            model = UserModel
            fields = ["id"]

    assert ExplicitMS._type_spec() == {"id": "int"}


def test_helpers_and_model_extract_fallback():
    opt = Field(alias="a")
    assert _input_key("x", opt) == "a"
    assert _extract_value({"a": {"b": 1}}, "a.b") == 1
    assert _extract_value({"a": 1}, "a") == 1
    assert _extract_value({"a": {"b": 1}}, "a.c") is None

    class UnknownModel:
        pass

    with pytest.raises(TypeError):
        _extract_model_types(UnknownModel)

    assert _django_type_to_python("CharField") is str
    assert _django_type_to_python("BooleanField") is bool
    assert _django_type_to_python("Nope") is None

    class FieldObj:
        def __init__(self, name, internal_type):
            self.name = name
            self._internal_type = internal_type

        def get_internal_type(self):
            return self._internal_type

    class MetaObj:
        @staticmethod
        def get_fields():
            return [
                FieldObj("title", "CharField"),
                FieldObj("skip", "Nope"),
                FieldObj("", "IntegerField"),
            ]

    class HasMeta:
        _meta = MetaObj()

    assert _extract_model_types(HasMeta) == {"title": str}


def test_model_serializer_missing_meta_model():
    class BadMS(ModelSerializer):
        pass

    with pytest.raises(TypeError):
        BadMS._model_class()


def test_field_names_meta_variants():
    class All(Serializer):
        a: int

    assert All._field_names() == ["a"]

    class Named(Serializer):
        a: int

        class Meta:
            fields = ("a",)

    assert Named._field_names() == ["a"]

    class Bad(Serializer):
        class Meta:
            fields = 123

    with pytest.raises(TypeError):
        Bad._field_names()


def test_extract_model_field_options_from_meta():
    class DummyValidator:
        def __call__(self, value):
            return value

    class FieldObj:
        def __init__(
            self,
            name,
            internal_type="CharField",
            blank=False,
            null=False,
            editable=True,
            default=None,
            choices=None,
            validators=None,
        ):
            self.name = name
            self._internal_type = internal_type
            self.blank = blank
            self.null = null
            self.editable = editable
            self.default = default
            self.choices = choices
            self.validators = validators or []
            self.max_length = 64
            self.auto_created = False
            self.concrete = True

        def get_internal_type(self):
            return self._internal_type

        def has_default(self):
            return self.default is not None

    class MetaObj:
        @staticmethod
        def get_fields():
            return [
                FieldObj("name", blank=False, null=False, default=None, choices=[("a", "A")], validators=[DummyValidator()]),
                FieldObj("note", blank=True, null=True, default="x"),
                FieldObj("skip", blank=True, null=True, default=None),
            ]

    class Model:
        _meta = MetaObj()

    opts = _extract_model_field_options(Model)
    assert opts["name"].required is True
    assert opts["name"].allow_null is False
    assert opts["name"].choices == ["a"]
    assert len(opts["name"].validators) == 1
    assert opts["note"].required is False
    assert opts["note"].allow_null is True
    assert opts["note"].default == "x"


def test_field_constraints_with_custom_validator():
    def validator(v):
        if v != "ok":
            raise ValueError("bad")

    class S(Serializer):
        name: str = Field(validators=[validator])

    assert S(data={"name": "ok"}).is_valid()
    assert not S(data={"name": "no"}).is_valid()


def test_extract_value_getattr_branch():
    class Obj:
        def __init__(self):
            self.a = type("B", (), {"c": 7})()

    assert _extract_value(Obj(), "a.c") == 7


def test_serializer_validation_error_class():
    err = ValidationError({"a": 1})
    assert err.detail == {"a": 1}


def test_optional_annotation_defaults_to_nullable_and_not_required():
    class OptSerializer(Serializer):
        note: str | None

    assert OptSerializer(data={}).is_valid()
    assert OptSerializer(data={"note": None}).is_valid()


def test_specialized_fields_validation():
    class S(Serializer):
        email: str = EmailField()
        url: str = URLField()
        uid: str = UUIDField()
        day: str = DateField()
        ts: str = DateTimeField()
        tm: str = TimeField()
        amount: str = DecimalField(max_digits=6, decimal_places=2)

    ok = S(
        data={
            "email": "a@example.com",
            "url": "https://example.com/x",
            "uid": "123e4567-e89b-12d3-a456-426614174000",
            "day": "2026-03-14",
            "ts": "2026-03-14T09:10:11Z",
            "tm": "09:10:11",
            "amount": "1234.56",
        }
    )
    assert ok.is_valid()
    bad = S(data={"email": "bad", "url": "x", "uid": "x", "day": "bad", "ts": "bad", "tm": "bad", "amount": "x"})
    assert not bad.is_valid()


def test_decimal_field_constraints():
    class S(Serializer):
        amount: str = DecimalField(max_digits=6, decimal_places=2, min_value=1, max_value=9999.99)

    assert S(data={"amount": "1234.56"}).is_valid()
    assert not S(data={"amount": "12345.67"}).is_valid()
    assert not S(data={"amount": "12.345"}).is_valid()
    assert not S(data={"amount": "0.99"}).is_valid()


def test_list_and_dict_fields_with_child_validation():
    class S(Serializer):
        tags: list = ListField(child=StringField(min_length=2), min_length=1, allow_empty=False)
        attrs: dict = DictField(value_field=IntegerField(min_value=1))

    ok = S(data={"tags": ["ab"], "attrs": {"a": 1}})
    assert ok.is_valid()
    bad_list = S(data={"tags": [""], "attrs": {"a": 1}})
    assert not bad_list.is_valid()
    bad_dict = S(data={"tags": ["ab"], "attrs": {"a": 0}})
    assert not bad_dict.is_valid()


def test_query_params_support_json_list_and_dict():
    class QS(Serializer):
        ids: list = ListField()
        opts: dict = DictField(required=False, default=dict)

    parsed = QS.parse_query_params({"ids": "[1,2,3]"})
    assert parsed["ids"] == [1, 2, 3]
    assert parsed["opts"] == {}


def test_django_field_to_serializer_field_mapping():
    assert _django_field_to_serializer_field("CharField") is StringField
    assert _django_field_to_serializer_field("IntegerField") is IntegerField
    assert _django_field_to_serializer_field("FloatField") is FloatField
    assert _django_field_to_serializer_field("BooleanField") is BooleanField
    assert _django_field_to_serializer_field("DecimalField") is DecimalField
