from __future__ import annotations

from pyferox import App
from pyferox.logging import install_logging_hooks


class CaptureLogger:
    def info(self, message: str, *, extra=None) -> None:  # type: ignore[no-untyped-def]
        return None

    def exception(self, message: str, *, extra=None) -> None:  # type: ignore[no-untyped-def]
        return None


def test_install_logging_hooks_with_request_middleware_enabled() -> None:
    app = App()
    install_logging_hooks(app, logger=CaptureLogger(), include_request_middleware=True)  # type: ignore[arg-type]
    assert len(app.dispatcher.middlewares) >= 1
