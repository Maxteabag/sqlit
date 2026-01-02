"""Azure cloud provider implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.widgets.option_list import Option

from ..base import (
    AccountInfo,
    CloudResource,
    ProviderState,
    ProviderStatus,
    SelectionResult,
)
from ..registry import register_provider

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


class AzureProvider:
    """Azure cloud provider for SQL database discovery."""

    # Option ID prefixes
    ACCOUNT_ID = "_azure_account"
    LOGIN_ID = "_azure_login"
    SUB_PREFIX = "_azure_sub_"
    SERVER_PREFIX = "_azure_server_"
    DB_PREFIX = "azure:"

    @property
    def name(self) -> str:
        return "Azure"

    @property
    def id(self) -> str:
        return "azure"

    @property
    def prefix(self) -> str:
        return "azure:"

    def get_status(self) -> ProviderStatus:
        """Check if Azure CLI is available and logged in."""
        from .cli import get_azure_status
        from .models import AzureStatus

        status = get_azure_status()
        return {
            AzureStatus.AVAILABLE: ProviderStatus.AVAILABLE,
            AzureStatus.NOT_LOGGED_IN: ProviderStatus.NOT_LOGGED_IN,
            AzureStatus.CLI_NOT_INSTALLED: ProviderStatus.CLI_NOT_INSTALLED,
            AzureStatus.ERROR: ProviderStatus.ERROR,
        }.get(status, ProviderStatus.ERROR)

    def get_account(self) -> AccountInfo | None:
        """Get the currently logged-in Azure account info."""
        from .cli import get_azure_account

        account = get_azure_account()
        if account is None:
            return None
        return AccountInfo(
            username=account.username,
            tenant=account.tenant_name,
        )

    def login(self) -> bool:
        """Initiate Azure CLI login. Returns True on success."""
        import subprocess

        try:
            result = subprocess.run(
                ["az", "login"],
                capture_output=True,
                timeout=300,
            )
            return result.returncode == 0
        except Exception:
            return False

    def logout(self) -> bool:
        """Log out from Azure CLI. Returns True on success."""
        from .cli import azure_logout

        return azure_logout()

    def discover(self, state: ProviderState) -> ProviderState:
        """Discover Azure SQL resources."""
        from .cache import cache_subscriptions_and_servers, get_cached_subscriptions
        from .cli import get_azure_subscriptions
        from .discovery import detect_azure_sql_resources
        from .models import AzureStatus

        # Get account info
        account = self.get_account()

        # Get subscriptions (from cache or fresh)
        subscriptions = get_cached_subscriptions()
        if subscriptions is None:
            subscriptions = get_azure_subscriptions()

        # Find default subscription
        default_sub_id = ""
        default_sub_index = 0
        for i, sub in enumerate(subscriptions):
            if sub.is_default:
                default_sub_id = sub.id
                default_sub_index = i
                break

        # Detect servers
        status, servers = detect_azure_sql_resources(default_sub_id, use_cache=True)

        # Cache results
        if subscriptions and default_sub_id:
            cache_subscriptions_and_servers(subscriptions, servers, default_sub_id)

        # Convert to provider status
        provider_status = {
            AzureStatus.AVAILABLE: ProviderStatus.AVAILABLE,
            AzureStatus.NOT_LOGGED_IN: ProviderStatus.NOT_LOGGED_IN,
            AzureStatus.CLI_NOT_INSTALLED: ProviderStatus.CLI_NOT_INSTALLED,
            AzureStatus.ERROR: ProviderStatus.ERROR,
        }.get(status, ProviderStatus.ERROR)

        # Build resources from subscriptions and servers
        resources = []
        for i, sub in enumerate(subscriptions):
            sub_resource = CloudResource(
                id=f"sub_{sub.id}",
                name=sub.name,
                resource_type="subscription",
                provider="azure",
                metadata={
                    "subscription_id": sub.id,
                    "is_default": sub.is_default,
                    "index": i,
                },
            )
            resources.append(sub_resource)

        # Add servers as top-level resources (they belong to the active subscription)
        for server in servers:
            server_resource = CloudResource(
                id=f"server_{server.name}",
                name=server.name,
                resource_type="server",
                provider="azure",
                metadata={
                    "fqdn": server.fqdn,
                    "resource_group": server.resource_group,
                    "subscription_id": server.subscription_id,
                    "subscription_name": server.subscription_name,
                    "location": server.location,
                    "admin_login": server.admin_login,
                },
                children=[
                    CloudResource(
                        id=f"db_{server.name}_{db}",
                        name=db,
                        resource_type="database",
                        provider="azure",
                        parent_id=f"server_{server.name}",
                        metadata={"server_name": server.name},
                    )
                    for db in server.databases
                ],
            )
            resources.append(server_resource)

        return ProviderState(
            status=provider_status,
            account=account,
            loading=False,
            resources=resources,
            extra={
                "subscriptions": subscriptions,
                "servers": servers,
                "current_subscription_index": default_sub_index,
            },
        )

    def build_options(
        self,
        state: ProviderState,
        saved_connections: list[ConnectionConfig],
        filter_pattern: str = "",
    ) -> list[Option]:
        """Build UI options for Azure resources."""
        from sqlit.shared.core.utils import fuzzy_match, highlight_matches

        options: list[Option] = []

        # Azure header
        options.append(Option("[bold]Azure[/]", id="_header_azure", disabled=True))

        # Loading state
        if state.loading:
            options.append(
                Option("[dim italic]  Loading...[/]", id="_azure_loading", disabled=True)
            )
            return options

        # Handle different statuses
        if state.status == ProviderStatus.CLI_NOT_INSTALLED:
            options.append(
                Option(
                    "  [dim](Azure CLI not installed)[/]",
                    id="_azure_cli_missing",
                    disabled=True,
                )
            )
            return options

        if state.status == ProviderStatus.NOT_LOGGED_IN:
            options.append(
                Option("  🔑 Login to Azure...", id=self.LOGIN_ID)
            )
            return options

        if state.status == ProviderStatus.ERROR:
            options.append(
                Option(
                    "  [red]⚠ Azure CLI error[/]",
                    id="_azure_error",
                    disabled=True,
                )
            )
            error_msg = state.error or "Try running 'az account show' in terminal"
            options.append(
                Option(f"    [dim]{error_msg}[/]", id="_azure_error_hint", disabled=True)
            )
            return options

        # Get subscriptions and servers from state
        subscriptions = state.extra.get("subscriptions", [])
        servers = state.extra.get("servers", [])
        current_sub_index = state.extra.get("current_subscription_index", 0)

        if not subscriptions:
            # Logged in but no subscriptions
            if state.account:
                account_display = state.account.username
                if len(account_display) > 40:
                    account_display = account_display[:37] + "..."
                options.append(
                    Option(f"  👤 {account_display}", id=self.ACCOUNT_ID)
                )
            options.append(
                Option(
                    "    [yellow]⚠ No subscriptions found[/]",
                    id="_azure_no_subs",
                    disabled=True,
                )
            )
            return options

        # Show account
        if state.account:
            account_display = state.account.username
            if len(account_display) > 40:
                account_display = account_display[:37] + "..."
            options.append(
                Option(f"  👤 {account_display}", id=self.ACCOUNT_ID)
            )

        # Show subscriptions (as children of account)
        for i, sub in enumerate(subscriptions):
            sub_display = f"{sub.name[:40]}..." if len(sub.name) > 40 else sub.name
            is_active = i == current_sub_index
            is_last_sub = i == len(subscriptions) - 1
            sub_branch = "└── " if is_last_sub else "├── "
            if is_active:
                options.append(
                    Option(
                        f"    {sub_branch}[green]🔑 ★ {sub_display}[/]",
                        id=f"{self.SUB_PREFIX}{i}",
                    )
                )
            else:
                options.append(
                    Option(
                        f"    {sub_branch}[dim]🔑 {sub_display}[/]",
                        id=f"{self.SUB_PREFIX}{i}",
                    )
                )

        # Show servers under active subscription
        if servers:
            # Filter servers first to know which is last
            filtered_servers = []
            for server in servers:
                matches, _ = fuzzy_match(filter_pattern, server.name)
                if matches or not filter_pattern:
                    filtered_servers.append(server)

            for server_idx, server in enumerate(filtered_servers):
                _, indices = fuzzy_match(filter_pattern, server.name)
                display = highlight_matches(server.name, indices) if filter_pattern else server.name
                # Status icon: 🟢 for Ready, 🟡 otherwise
                status_icon = "🟢" if server.state == "Ready" else "🟡"
                is_last_server = server_idx == len(filtered_servers) - 1
                server_branch = "└── " if is_last_server else "├── "
                server_cont = "    " if is_last_server else "│   "

                # Auth method indicator
                if server.entra_only_auth:
                    auth_hint = " [dim][Entra only][/]"
                elif server.has_entra_admin:
                    auth_hint = ""  # Both available, no need for hint
                else:
                    auth_hint = " [dim][SQL only][/]"

                if server.databases:
                    # Server header with status
                    options.append(
                        Option(
                            f"        {server_branch}{status_icon} {display}{auth_hint}",
                            id=f"{self.SERVER_PREFIX}{server.name}",
                            disabled=True,
                        )
                    )

                    # Build list of database options based on available auth methods
                    db_options = []
                    for db in server.databases:
                        db_matches, db_indices = fuzzy_match(filter_pattern, db)
                        if not db_matches and filter_pattern:
                            continue
                        db_display = highlight_matches(db, db_indices) if filter_pattern else db

                        # Only show Entra option if Entra admin is configured
                        if server.has_entra_admin:
                            ad_saved = self._is_connection_saved(server, db, False, saved_connections)
                            db_options.append((db, db_display, "ad", ad_saved))

                        # Only show SQL Auth option if not Entra-only
                        if not server.entra_only_auth:
                            sql_saved = self._is_connection_saved(server, db, True, saved_connections)
                            db_options.append((db, db_display, "sql", sql_saved))

                    # Render database options with tree lines
                    for db_idx, (db, db_display, auth_type, is_saved) in enumerate(db_options):
                        is_last_db = db_idx == len(db_options) - 1
                        db_branch = "└── " if is_last_db else "├── "
                        auth_label = "Entra" if auth_type == "ad" else "SQL Auth"

                        if is_saved:
                            options.append(
                                Option(
                                    f"        {server_cont}{db_branch}[dim]{db_display} {auth_label} ✓[/]",
                                    id=f"{self.DB_PREFIX}{server.name}:{db}:{auth_type}",
                                )
                            )
                        else:
                            options.append(
                                Option(
                                    f"        {server_cont}{db_branch}{db_display} [dim]{auth_label}[/]",
                                    id=f"{self.DB_PREFIX}{server.name}:{db}:{auth_type}",
                                )
                            )
                else:
                    # Server with no databases loaded yet
                    options.append(
                        Option(
                            f"        {server_branch}{status_icon} {display}{auth_hint} [dim](no databases)[/]",
                            id=f"{self.SERVER_PREFIX}empty_{server.name}",
                            disabled=True,
                        )
                    )
        else:
            options.append(
                Option(
                    "        [dim](no SQL servers in this subscription)[/]",
                    id="_azure_no_servers",
                    disabled=True,
                )
            )

        return options

    def get_shortcuts(
        self,
        option_id: str,
        state: ProviderState,
    ) -> list[tuple[str, str]]:
        """Get keyboard shortcuts for the selected option."""
        if option_id == self.ACCOUNT_ID:
            return [("Logout", "l"), ("Switch", "w")]
        return []

    def handle_action(
        self,
        action: str,
        option_id: str,
        state: ProviderState,
        saved_connections: list[ConnectionConfig],
    ) -> SelectionResult:
        """Handle an action on an Azure option."""
        # Login action
        if option_id == self.LOGIN_ID:
            return SelectionResult(action="login")

        # Account actions
        if option_id == self.ACCOUNT_ID:
            if action == "logout":
                return SelectionResult(action="logout")
            elif action == "switch":
                return SelectionResult(action="login")  # Switch = re-login
            return SelectionResult(action="none")

        # Subscription selection
        if option_id.startswith(self.SUB_PREFIX):
            sub_index = int(option_id.replace(self.SUB_PREFIX, ""))
            return SelectionResult(
                action="switch_subscription",
                metadata={"subscription_index": sub_index},
            )

        # Database selection
        if option_id.startswith(self.DB_PREFIX):
            server_name, database, auth_type = self._parse_db_option_id(option_id)
            servers = state.extra.get("servers", [])
            server = next((s for s in servers if s.name == server_name), None)

            if server:
                use_sql_auth = auth_type == "sql"
                config = self._server_to_config(server, database, use_sql_auth)

                if action == "save":
                    return SelectionResult(
                        action="save",
                        config=config,
                    )
                else:
                    return SelectionResult(
                        action="connect",
                        config=config,
                    )

        return SelectionResult(action="none")

    def is_my_option(self, option_id: str) -> bool:
        """Check if an option ID belongs to this provider."""
        if option_id is None:
            return False
        option_id = str(option_id)
        return (
            option_id.startswith(self.DB_PREFIX)
            or option_id.startswith(self.SUB_PREFIX)
            or option_id.startswith(self.SERVER_PREFIX)
            or option_id in (self.ACCOUNT_ID, self.LOGIN_ID)
            or option_id.startswith("_azure_")
        )

    def is_saved(
        self,
        resource: CloudResource,
        saved_connections: list[ConnectionConfig],
    ) -> bool:
        """Check if a resource is already saved."""
        # This is handled in _is_connection_saved for databases
        return False

    def resource_to_config(
        self,
        resource: CloudResource,
        **kwargs: Any,
    ) -> ConnectionConfig:
        """Convert a cloud resource to a connection config."""
        # Use _server_to_config for actual conversion
        raise NotImplementedError("Use handle_action for config creation")

    def _is_connection_saved(
        self,
        server: Any,
        database: str,
        use_sql_auth: bool,
        saved_connections: list[ConnectionConfig],
    ) -> bool:
        """Check if an Azure connection is already saved."""
        auth_type = "sql" if use_sql_auth else "ad_default"
        for conn in saved_connections:
            if conn.source != "azure":
                continue
            endpoint = conn.tcp_endpoint
            if not endpoint or endpoint.host != server.fqdn:
                continue
            if endpoint.database != database:
                continue
            conn_auth = conn.get_option("auth_type")
            if conn_auth == auth_type:
                return True
        return False

    def _parse_db_option_id(self, option_id: str) -> tuple[str, str, str]:
        """Parse a database option ID into (server_name, database, auth_type)."""
        # Format: azure:server_name:database:auth_type
        parts = option_id.replace(self.DB_PREFIX, "").split(":")
        if len(parts) >= 3:
            return parts[0], parts[1], parts[2]
        return "", "", ""

    def _server_to_config(
        self,
        server: Any,
        database: str | None,
        use_sql_auth: bool,
    ) -> ConnectionConfig:
        """Convert an Azure SQL server to a connection config."""
        from sqlit.domains.connections.domain.config import ConnectionConfig

        azure_options = {
            "azure_server_name": server.name,
            "azure_resource_group": server.resource_group,
            "azure_subscription_id": server.subscription_id,
        }

        return ConnectionConfig.from_dict(
            {
                "name": f"{server.name}/{database}" if database else server.name,
                "db_type": "mssql",
                "endpoint": {
                    "kind": "tcp",
                    "host": server.fqdn,
                    "port": "1433",
                    "database": database or "master",
                    "username": server.admin_login or "" if use_sql_auth else "",
                    "password": None,
                },
                "source": "azure",
                "options": {
                    "auth_type": "sql" if use_sql_auth else "ad_default",
                    **azure_options,
                },
            }
        )


# Register the provider
_provider = AzureProvider()
register_provider(_provider)
