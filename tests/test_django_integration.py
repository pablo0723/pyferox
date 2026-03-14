import asyncio
import unittest

from django.conf import settings

if not settings.configured:
    settings.configure(
        SECRET_KEY="test",
        ALLOWED_HOSTS=["*"],
        ROOT_URLCONF=__name__,
        MIDDLEWARE=[],
        INSTALLED_APPS=["django.contrib.contenttypes", "django.contrib.auth"],
    )

import django
from django.test import AsyncRequestFactory

django.setup()

from pyferox import API, HTTPError, as_django_view


class DjangoIntegrationTests(unittest.TestCase):
    def test_django_adapter(self):
        app = API()

        @app.get("/api/users/{user_id}")
        async def get_user(request):
            if request.path_params["user_id"] != "1":
                raise HTTPError(404, "not found")
            return {"id": 1, "name": "Ada"}

        view = as_django_view(app)
        request = AsyncRequestFactory().get("/api/users/1")
        response = asyncio.run(view(request))
        self.assertEqual(response.status_code, 200)
        self.assertIn('"name":"Ada"', response.content.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
