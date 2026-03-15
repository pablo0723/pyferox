from __future__ import annotations

from dataclasses import dataclass

from pyferox import Command, Module, handle, provider
from pyferox.testing import TestHTTPClient, create_test_app, override_dependencies


@dataclass(slots=True)
class Echo(Command):
    text: str


@handle(Echo)
async def echo_handler(cmd: Echo) -> dict[str, str]:
    return {"text": cmd.text}


def test_test_http_client_works() -> None:
    app = create_test_app(modules=[Module(handlers=[echo_handler])])
    client = TestHTTPClient(app)
    client.command("POST", "/echo", Echo, status_code=200)
    response = client.request("POST", "/echo", body={"text": "hello"})
    assert response["status"] == 200
    assert response["json"] == {"text": "hello"}


class Greeter:
    def greet(self) -> str:
        return "hello"


@dataclass(slots=True)
class Greet(Command):
    pass


@handle(Greet)
async def greet_handler(cmd: Greet, greeter: Greeter) -> dict[str, str]:
    return {"text": greeter.greet()}


def test_override_dependencies() -> None:
    app = create_test_app(modules=[Module(handlers=[greet_handler], providers=[provider(Greeter, lambda: Greeter())])])
    client = TestHTTPClient(app)
    client.command("POST", "/greet", Greet, status_code=200)

    class TestGreeter(Greeter):
        def greet(self) -> str:
            return "test-hi"

    with override_dependencies(app, provider(Greeter, lambda: TestGreeter())):
        response = client.request("POST", "/greet", body={})
    assert response["json"] == {"text": "test-hi"}
