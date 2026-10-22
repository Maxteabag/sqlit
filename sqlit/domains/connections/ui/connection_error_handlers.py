"""Error handling strategies for connection failures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

from sqlit.shared.ui.protocols import ConnectionsProtocol, TextualAppProtocol

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


class ConnectionErrorApp(TextualAppProtocol, ConnectionsProtocol, Protocol):
    """Subset of App behavior required for connection error handling."""

    pass


class ConnectionErrorHandler(Protocol):
    def can_handle(self, error: Exception) -> bool:
        """Return True if this handler can handle the error."""
        ...

    def handle(self, app: ConnectionErrorApp, error: Exception, config: ConnectionConfig) -> None:
        """Handle the error."""
        ...


@dataclass(frozen=True)
class MissingDriverHandler:
    def can_handle(self, error: Exception) -> bool:
        from sqlit.domains.connections.providers.exceptions import MissingDriverError

        return isinstance(error, MissingDriverError)

    def handle(self, app: ConnectionErrorApp, error: Exception, config: ConnectionConfig) -> None:
        from sqlit.domains.connections.providers.exceptions import MissingDriverError
        from sqlit.shared.core.debug_events import emit_debug_event

        from .restart_cache import write_pending_connection_cache
        from .screens import PackageSetupScreen

        # Save pending connection for auto-reconnect after driver install restart
        if config.name:
            write_pending_connection_cache(config.name)
            emit_debug_event(
                "driver_install.pending_connection_saved",
                connection_name=config.name,
            )

        # No on_success callback - uses default "Restart to apply" behavior
        app.push_screen(PackageSetupScreen(cast(MissingDriverError, error)))


@dataclass(frozen=True)
class AzureFirewallHandler:
    """Handle Azure SQL firewall errors by offering to add a firewall rule."""

    def can_handle(self, error: Exception) -> bool:
        from sqlit.domains.connections.discovery.cloud.azure.firewall import is_firewall_error

        return is_firewall_error(str(error))

    def handle(self, app: ConnectionErrorApp, error: Exception, config: ConnectionConfig) -> None:
        from sqlit.domains.connections.discovery.cloud.azure.firewall import (
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
            endpoint = config.tcp_endpoint
            short_name = parse_server_name_from_hostname(endpoint.host if endpoint else "")
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


_UNTRUSTED_CERT_MARKERS = (
    "certificate verify failed",
    "certificate chain was issued by an authority that is not trusted",
)


def is_untrusted_certificate_error(message: str) -> bool:
    text = message.lower()
    return any(marker in text for marker in _UNTRUSTED_CERT_MARKERS)


@dataclass(frozen=True)
class UntrustedServerCertificateHandler:
    """Offer to trust a SQL Server certificate that cannot be verified.

    SQL Server verifies the server certificate by default. A server with a
    self-signed certificate then fails to connect; ask once, and remember the
    answer on the connection, the way SSH asks about an unknown host key.
    """

    def can_handle(self, error: Exception) -> bool:
        return is_untrusted_certificate_error(str(error))

    def handle(self, app: ConnectionErrorApp, error: Exception, config: ConnectionConfig) -> None:
        from sqlit.shared.ui.screens.confirm import ConfirmScreen
        from sqlit.shared.ui.screens.error import ErrorScreen

        if config.db_type != "mssql":
            app.push_screen(ErrorScreen("Connection Failed", str(error)))
            return

        endpoint = config.tcp_endpoint
        host = endpoint.host if endpoint else "The server"

        def on_result(confirmed: bool | None) -> None:
            if not confirmed:
                return
            trust_server_certificate(app, config)
            app.connect_to_server(config)

        app.push_screen(
            ConfirmScreen(
                "Untrusted server certificate",
                f"{host} presented a certificate that can't be verified, "
                "usually because it is self-signed.\n\n"
                "Trust it for this connection? Only do this for a server you know: "
                "on an untrusted network, someone could be impersonating it.",
                yes_label="Trust this server",
                no_label="Cancel",
            ),
            on_result,
        )


def trust_server_certificate(app: ConnectionErrorApp, config: ConnectionConfig) -> None:
    """Encrypt without verifying the certificate, and save that on the connection."""
    from sqlit.domains.connections.providers.tls import TLS_MODE_REQUIRE

    config.set_option("tls_mode", TLS_MODE_REQUIRE)
    config.set_option("tls_trust_server_certificate", "yes")
    if not config.name or all(c.name != config.name for c in app.connections):
        return
    app.connections = [config if c.name == config.name else c for c in app.connections]
    try:
        app.services.connection_store.save_one(config)
    except Exception as exc:
        app.notify(f"Trusted for this session, but could not save: {exc}", severity="warning")


_DEFAULT_HANDLERS: tuple[ConnectionErrorHandler, ...] = (
    AzureFirewallHandler(),
    MissingDriverHandler(),
    UntrustedServerCertificateHandler(),
)


def handle_connection_error(app: ConnectionErrorApp, error: Exception, config: ConnectionConfig) -> bool:
    for handler in _DEFAULT_HANDLERS:
        if handler.can_handle(error):
            handler.handle(app, error, config)
            return True
    return False
