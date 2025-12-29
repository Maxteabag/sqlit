"""GCP cloud provider implementation."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
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
    from ....config import ConnectionConfig


@dataclass
class GCPCloudSQLInstance:
    """Represents a GCP Cloud SQL instance."""

    name: str
    database_version: str  # MYSQL_8_0, POSTGRES_14, SQLSERVER_2019_STANDARD, etc.
    connection_name: str  # project:region:instance
    ip_address: str | None
    state: str
    region: str
    project: str


class GCPProvider:
    """GCP cloud provider for Cloud SQL database discovery."""

    # Option ID prefixes
    ACCOUNT_ID = "_gcp_account"
    LOGIN_ID = "_gcp_login"
    INSTANCE_PREFIX = "gcp:sql:"
    PROJECT_PREFIX = "_gcp_project_"

    # Map Cloud SQL database version to our db_type
    ENGINE_MAP = {
        "MYSQL": "mysql",
        "POSTGRES": "postgresql",
        "SQLSERVER": "mssql",
    }

    @property
    def name(self) -> str:
        return "GCP"

    @property
    def id(self) -> str:
        return "gcp"

    @property
    def prefix(self) -> str:
        return "gcp:"

    def get_status(self) -> ProviderStatus:
        """Check if gcloud CLI is available and logged in."""
        try:
            result = subprocess.run(
                ["gcloud", "--version"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode != 0:
                return ProviderStatus.CLI_NOT_INSTALLED
        except FileNotFoundError:
            return ProviderStatus.CLI_NOT_INSTALLED
        except Exception:
            return ProviderStatus.ERROR

        # Check if logged in
        try:
            result = subprocess.run(
                ["gcloud", "auth", "list", "--format=json"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode != 0:
                return ProviderStatus.ERROR

            accounts = json.loads(result.stdout.decode())
            # Check if any account is active
            active = any(acc.get("status") == "ACTIVE" for acc in accounts)
            if active:
                return ProviderStatus.AVAILABLE
            return ProviderStatus.NOT_LOGGED_IN
        except Exception:
            return ProviderStatus.ERROR

    def get_account(self) -> AccountInfo | None:
        """Get the currently logged-in GCP account info."""
        try:
            # Get active account
            result = subprocess.run(
                ["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=json"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode != 0:
                return None

            accounts = json.loads(result.stdout.decode())
            if not accounts:
                return None

            account = accounts[0].get("account", "")

            # Get current project
            project_result = subprocess.run(
                ["gcloud", "config", "get-value", "project"],
                capture_output=True,
                timeout=5,
            )
            project = project_result.stdout.decode().strip() if project_result.returncode == 0 else None

            return AccountInfo(
                username=account,
                display_name=account,
                tenant=project,  # Using tenant for project
            )
        except Exception:
            return None

    def login(self) -> bool:
        """Initiate gcloud CLI login. Returns True on success."""
        try:
            result = subprocess.run(
                ["gcloud", "auth", "login"],
                capture_output=True,
                timeout=300,
            )
            return result.returncode == 0
        except Exception:
            return False

    def logout(self) -> bool:
        """Log out from gcloud CLI. Returns True on success."""
        from .cache import clear_gcp_cache

        try:
            result = subprocess.run(
                ["gcloud", "auth", "revoke"],
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0:
                clear_gcp_cache()
                return True
            return False
        except Exception:
            return False

    def discover(self, state: ProviderState, use_cache: bool = True) -> ProviderState:
        """Discover GCP Cloud SQL resources."""
        from .cache import load_cached_data, save_gcp_cache

        # Try cache first - this is fast and avoids CLI calls
        cached = None
        if use_cache:
            cached = load_cached_data()

        if cached is not None:
            # Cache hit - use cached data without any CLI calls
            project, instances, account_username = cached
            account = AccountInfo(
                username=account_username or "",
                display_name=account_username,
                tenant=project,
            ) if account_username else None
        else:
            # No cache - full check and discovery
            status = self.get_status()
            if status != ProviderStatus.AVAILABLE:
                return ProviderState(status=status, loading=False)

            account = self.get_account()

            # Get current project
            project = self._get_current_project()
            if not project:
                return ProviderState(
                    status=ProviderStatus.ERROR,
                    account=account,
                    loading=False,
                    error="No project configured. Run: gcloud config set project PROJECT_ID",
                )

            # Discover fresh
            instances = self._discover_cloud_sql_instances(project)
            save_gcp_cache(project, instances, account.username if account else None)

        # Build resources
        resources: list[CloudResource] = []

        for instance in instances:
            resources.append(
                CloudResource(
                    id=f"sql_{instance.name}",
                    name=instance.name,
                    resource_type="cloud_sql_instance",
                    provider="gcp",
                    metadata={
                        "database_version": instance.database_version,
                        "connection_name": instance.connection_name,
                        "ip_address": instance.ip_address,
                        "state": instance.state,
                        "region": instance.region,
                        "project": instance.project,
                    },
                )
            )

        return ProviderState(
            status=ProviderStatus.AVAILABLE,
            account=account,
            loading=False,
            resources=resources,
            extra={
                "instances": instances,
                "project": project,
            },
        )

    def _get_current_project(self) -> str | None:
        """Get the current GCP project."""
        try:
            result = subprocess.run(
                ["gcloud", "config", "get-value", "project"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                project = result.stdout.decode().strip()
                return project if project else None
        except Exception:
            pass
        return None

    def _discover_cloud_sql_instances(self, project: str) -> list[GCPCloudSQLInstance]:
        """Discover Cloud SQL instances in the given project."""
        instances: list[GCPCloudSQLInstance] = []

        try:
            result = subprocess.run(
                [
                    "gcloud", "sql", "instances", "list",
                    "--project", project,
                    "--format=json",
                ],
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                return instances

            data = json.loads(result.stdout.decode())
            for inst in data:
                # Get primary IP address
                ip_address = None
                ip_addresses = inst.get("ipAddresses", [])
                for ip in ip_addresses:
                    if ip.get("type") == "PRIMARY":
                        ip_address = ip.get("ipAddress")
                        break

                instances.append(
                    GCPCloudSQLInstance(
                        name=inst.get("name", ""),
                        database_version=inst.get("databaseVersion", ""),
                        connection_name=inst.get("connectionName", ""),
                        ip_address=ip_address,
                        state=inst.get("state", ""),
                        region=inst.get("region", ""),
                        project=project,
                    )
                )
        except Exception:
            pass

        return instances

    def _get_db_type(self, database_version: str) -> str:
        """Get our db_type from GCP database version."""
        # database_version is like MYSQL_8_0, POSTGRES_14, SQLSERVER_2019_STANDARD
        for prefix, db_type in self.ENGINE_MAP.items():
            if database_version.startswith(prefix):
                return db_type
        return "postgresql"  # Default fallback

    def _get_default_port(self, database_version: str) -> str:
        """Get default port for database type."""
        if database_version.startswith("MYSQL"):
            return "3306"
        elif database_version.startswith("POSTGRES"):
            return "5432"
        elif database_version.startswith("SQLSERVER"):
            return "1433"
        return "5432"

    def build_options(
        self,
        state: ProviderState,
        saved_connections: list[ConnectionConfig],
        filter_pattern: str = "",
    ) -> list[Option]:
        """Build UI options for GCP resources."""
        from ....utils import fuzzy_match, highlight_matches

        options: list[Option] = []

        # GCP header
        options.append(Option("[bold]GCP[/]", id="_header_gcp", disabled=True))

        # Loading state
        if state.loading:
            options.append(
                Option("[dim italic]  Loading...[/]", id="_gcp_loading", disabled=True)
            )
            return options

        # Handle different statuses
        if state.status == ProviderStatus.CLI_NOT_INSTALLED:
            options.append(
                Option(
                    "  [dim](gcloud CLI not installed)[/]",
                    id="_gcp_cli_missing",
                    disabled=True,
                )
            )
            return options

        if state.status == ProviderStatus.NOT_LOGGED_IN:
            options.append(
                Option("  🔑 Login to GCP...", id=self.LOGIN_ID)
            )
            return options

        if state.status == ProviderStatus.ERROR:
            options.append(
                Option(
                    "  [red]⚠ GCP error[/]",
                    id="_gcp_error",
                    disabled=True,
                )
            )
            error_msg = state.error or "Check gcloud configuration"
            options.append(
                Option(f"    [dim]{error_msg}[/]", id="_gcp_error_hint", disabled=True)
            )
            return options

        if state.status == ProviderStatus.NOT_SUPPORTED:
            options.append(
                Option("[dim]  (coming soon)[/]", id="_gcp_coming_soon", disabled=True)
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

        # Show project
        project = state.extra.get("project", "")
        if project:
            options.append(
                Option(f"    [dim]Project: {project}[/]", id="_gcp_project_info", disabled=True)
            )

        # Get instances
        instances = state.extra.get("instances", [])

        # Cloud SQL Instances
        if instances:
            options.append(
                Option("    [bold]Cloud SQL Instances[/]", id="_gcp_sql_header", disabled=True)
            )
            for instance in instances:
                matches, indices = fuzzy_match(filter_pattern, instance.name)
                if not matches and filter_pattern:
                    continue

                display = (
                    highlight_matches(instance.name, indices)
                    if filter_pattern
                    else instance.name
                )

                # Parse engine from database_version
                engine_display = instance.database_version.replace("_", " ")
                status_icon = "🟢" if instance.state == "RUNNABLE" else "🟡"
                saved = self._is_instance_saved(instance, saved_connections)

                if saved:
                    options.append(
                        Option(
                            f"      [dim]{status_icon} {display} [{engine_display}] ✓[/]",
                            id=f"{self.INSTANCE_PREFIX}{instance.name}",
                        )
                    )
                else:
                    options.append(
                        Option(
                            f"      {status_icon} {display} [dim][{engine_display}][/]",
                            id=f"{self.INSTANCE_PREFIX}{instance.name}",
                        )
                    )
        else:
            options.append(
                Option(
                    "    [dim](no Cloud SQL instances in this project)[/]",
                    id="_gcp_no_instances",
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
        """Handle an action on a GCP option."""
        # Login action
        if option_id == self.LOGIN_ID:
            return SelectionResult(action="login")

        # Account actions
        if option_id == self.ACCOUNT_ID:
            if action == "logout":
                return SelectionResult(action="logout")
            elif action == "switch":
                return SelectionResult(action="login")
            return SelectionResult(action="none")

        # Cloud SQL instance selection
        if option_id.startswith(self.INSTANCE_PREFIX):
            instance_name = option_id.replace(self.INSTANCE_PREFIX, "")
            instances = state.extra.get("instances", [])
            instance = next((i for i in instances if i.name == instance_name), None)

            if instance:
                config = self._instance_to_config(instance)
                if action == "save":
                    if self._is_instance_saved(instance, saved_connections):
                        return SelectionResult(action="none")
                    return SelectionResult(action="save", config=config)
                return SelectionResult(action="connect", config=config)

        return SelectionResult(action="none")

    def is_my_option(self, option_id: str) -> bool:
        """Check if an option ID belongs to this provider."""
        if option_id is None:
            return False
        option_id = str(option_id)
        return (
            option_id.startswith(self.INSTANCE_PREFIX)
            or option_id in (self.ACCOUNT_ID, self.LOGIN_ID)
            or option_id.startswith("_gcp_")
        )

    def is_saved(
        self,
        resource: CloudResource,
        saved_connections: list[ConnectionConfig],
    ) -> bool:
        """Check if a resource is already saved."""
        return False

    def resource_to_config(
        self,
        resource: CloudResource,
        **kwargs: Any,
    ) -> ConnectionConfig:
        """Convert a cloud resource to a connection config."""
        raise NotImplementedError("Use handle_action for config creation")

    def _is_instance_saved(
        self,
        instance: GCPCloudSQLInstance,
        saved_connections: list[ConnectionConfig],
    ) -> bool:
        """Check if a Cloud SQL instance is already saved."""
        for conn in saved_connections:
            if conn.source != "gcp":
                continue
            # Check by connection name or IP
            if conn.options.get("gcp_connection_name") == instance.connection_name:
                return True
            if instance.ip_address and conn.server == instance.ip_address:
                return True
        return False

    def _instance_to_config(self, instance: GCPCloudSQLInstance) -> ConnectionConfig:
        """Convert a Cloud SQL instance to a connection config."""
        from ....config import ConnectionConfig

        db_type = self._get_db_type(instance.database_version)
        port = self._get_default_port(instance.database_version)

        # Use IP address if available, otherwise connection name
        server = instance.ip_address or instance.connection_name

        return ConnectionConfig(
            name=instance.name,
            db_type=db_type,
            server=server,
            port=port,
            database="",  # User needs to specify
            username="",  # User needs to specify
            password=None,
            source="gcp",
            options={
                "gcp_connection_name": instance.connection_name,
                "gcp_project": instance.project,
                "gcp_region": instance.region,
                "gcp_database_version": instance.database_version,
            },
        )


# Register the provider
_provider = GCPProvider()
register_provider(_provider)
