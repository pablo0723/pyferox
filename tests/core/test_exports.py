import pyferox
import pyferox.core as core
import pyferox.django as dj


def test_top_level_exports():
    assert pyferox.API is pyferox.DjangoAPI
    assert "Serializer" in pyferox.__all__
    assert "EmailField" in pyferox.__all__
    assert "as_django_view" in pyferox.__all__


def test_core_exports():
    assert "Serializer" in core.__all__
    assert "Schema" in core.__all__
    assert "ListField" in core.__all__


def test_django_exports():
    assert "DjangoAPI" in dj.__all__
    assert "as_django_view" in dj.__all__
