import django
import pytest
from django.conf import settings


@pytest.fixture(scope="session", autouse=True)
def django_settings():
    if not settings.configured:
        settings.configure(
            SECRET_KEY="test-secret",
            ALLOWED_HOSTS=["*"],
            ROOT_URLCONF=__name__,
            MIDDLEWARE=[],
            INSTALLED_APPS=[
                "django.contrib.auth",
                "django.contrib.contenttypes",
            ],
        )
    django.setup()
    return settings
