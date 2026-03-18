from __future__ import annotations

from pyferox.core import App
from pyferox.http import HTTPAdapter

from app.billing import GetBalance, billing_module
from app.users import CreateUser, GetUser, users_module

app = App(modules=[users_module, billing_module])
http = HTTPAdapter(app)

http.command("POST", "/users", CreateUser, status_code=201)
http.query("GET", "/users/{user_id}", GetUser)
http.query("GET", "/billing/{user_id}/balance", GetBalance)
http.enable_openapi(path="/openapi.json", title="PyFerOx Reference Service", version="0.1.0")
