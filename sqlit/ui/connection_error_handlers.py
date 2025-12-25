"""Error handling strategies for connection failures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TYPE_CHECKING

from .protocols import AppProtocol

if TYPE_CHECKING:
    from ..config import ConnectionConfig


class ConnectionErrorHandler(Protocol):
    def can_handle(self, error: Exception) -> bool:
        """Return True if this handler can handle the error."""

    def handle(self, app: AppProtocol, error: Exception, config: ConnectionConfig) -> None:
        """Handle the error."""


@dataclass(frozen=True)
class MissingDriverHandler:
    def can_handle(self, error: Exception) -> bool:
        from ..db.exceptions import MissingDriverError

        return isinstance(error, MissingDriverError)

    def handle(self, app: AppProtocol, error: Exception, config: ConnectionConfig) -> None:
        from ..services.installer import Installer
        from .screens import PackageSetupScreen

        app.push_screen(
            PackageSetupScreen(error, on_install=lambda err: Installer(app).install(err)),
        )


_DEFAULT_HANDLERS: tuple[ConnectionErrorHandler, ...] = (
    MissingDriverHandler(),
)


def handle_connection_error(app: AppProtocol, error: Exception, config: ConnectionConfig) -> bool:
    for handler in _DEFAULT_HANDLERS:
        if handler.can_handle(error):
            handler.handle(app, error, config)
            return True
    return False
