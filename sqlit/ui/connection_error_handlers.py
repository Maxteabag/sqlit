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
        from .screens import PackageSetupScreen

        # No on_success callback - uses default "Restart to apply" behavior
        app.push_screen(PackageSetupScreen(error))


@dataclass(frozen=True)
class AzureFirewallHandler:
    """Handle Azure SQL firewall errors by offering to add a firewall rule."""

    def can_handle(self, error: Exception) -> bool:
        from ..services.cloud_detector import is_firewall_error

        return is_firewall_error(str(error))

    def handle(self, app: AppProtocol, error: Exception, config: ConnectionConfig) -> None:
        from ..services.cloud_detector import (
            lookup_azure_sql_server,
            parse_ip_from_firewall_error,
            parse_server_name_from_hostname,
        )
        from .screens import AzureFirewallScreen

        ip_address = parse_ip_from_firewall_error(str(error))
        if not ip_address:
            return

        # Try to get Azure metadata from config (cloud-discovered connections)
        server_name = config.get_option("azure_server_name")
        resource_group = config.get_option("azure_resource_group")
        subscription_id = config.get_option("azure_subscription_id")

        # If metadata not available, try to look up from hostname
        if not server_name or not resource_group:
            short_name = parse_server_name_from_hostname(config.server or "")
            if short_name:
                azure_server = lookup_azure_sql_server(short_name)
                if azure_server:
                    server_name = azure_server.name
                    resource_group = azure_server.resource_group
                    subscription_id = azure_server.subscription_id

        # Still no metadata - can't add firewall rule
        if not server_name or not resource_group:
            return

        def on_result(added: bool) -> None:
            if added:
                # Retry connection after firewall rule added
                app.connect_to_server(config)

        app.push_screen(
            AzureFirewallScreen(
                server_name=server_name,
                resource_group=resource_group,
                subscription_id=subscription_id,
                ip_address=ip_address,
            ),
            on_result,
        )


_DEFAULT_HANDLERS: tuple[ConnectionErrorHandler, ...] = (
    AzureFirewallHandler(),
    MissingDriverHandler(),
)


def handle_connection_error(app: AppProtocol, error: Exception, config: ConnectionConfig) -> bool:
    for handler in _DEFAULT_HANDLERS:
        if handler.can_handle(error):
            handler.handle(app, error, config)
            return True
    return False
