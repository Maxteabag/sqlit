"""Connection picker screen with fuzzy search and Docker/Cloud detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.events import Key
from textual.screen import ModalScreen
from textual.worker import Worker
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from ...db.providers import get_connection_display_info
from ...utils import fuzzy_match, highlight_matches
from ...widgets import Dialog, FilterInput

if TYPE_CHECKING:
    from ...config import ConnectionConfig
    from ...services.cloud_detector import AzureAccount, AzureSqlServer, AzureStatus, AzureSubscription
    from ...services.docker_detector import DetectedContainer, DockerStatus


@dataclass
class DockerConnectionResult:
    """Result when selecting a Docker container."""

    container: DetectedContainer
    action: str  # "connect" or "save"

    def get_result_kind(self) -> str:
        return "docker"


@dataclass
class AzureConnectionResult:
    """Result when selecting an Azure SQL resource."""

    server: AzureSqlServer
    database: str | None = None
    use_sql_auth: bool = False  # False = AD auth, True = SQL Server auth

    def get_result_kind(self) -> str:
        return "azure"


class ConnectionPickerScreen(ModalScreen):
    """Modal screen for selecting a connection with fuzzy search."""

    BINDINGS = [
        Binding("escape", "cancel_or_close_filter", "Cancel"),
        Binding("enter", "select", "Select"),
        Binding("s", "save_docker", "Save", show=False),
        Binding("n", "new_connection", "New", show=False),
        Binding("f", "refresh", "Refresh", show=False),
        Binding("slash", "open_filter", "Search", show=False),
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("backspace", "backspace", "Backspace", show=False),
        Binding("tab", "switch_tab", "Switch Tab", show=False),
        Binding("l", "azure_logout", "Logout", show=False),
        Binding("w", "azure_switch", "Switch", show=False),
    ]

    CSS = """
    ConnectionPickerScreen {
        align: center middle;
        background: transparent;
    }

    #picker-dialog {
        width: 75;
        max-width: 90%;
        height: auto;
        max-height: 70%;
    }

    #picker-list {
        height: 20;
        background: $surface;
        border: none;
        padding: 0;
    }

    #picker-list > .option-list--option {
        padding: 0 1;
    }

    #picker-empty {
        text-align: center;
        color: $text-muted;
        padding: 2;
    }

    .section-header {
        color: $text-muted;
        padding: 0 1;
        margin-top: 1;
    }

    .section-header-first {
        color: $text-muted;
        padding: 0 1;
    }

    #picker-filter {
        height: 1;
        background: $surface;
        padding: 0 1;
        margin-bottom: 1;
    }
    """

    # Prefix for Docker container option IDs
    DOCKER_PREFIX = "docker:"
    # Prefix for Azure resource option IDs
    AZURE_PREFIX = "azure:"

    # Tab names
    TAB_CONNECTIONS = "connections"
    TAB_DOCKER = "docker"
    TAB_CLOUD = "cloud"

    def __init__(self, connections: list[ConnectionConfig]):
        super().__init__()
        self.connections = connections
        self.search_text = ""
        self._filter_active = False
        self._current_tab = self.TAB_CONNECTIONS  # Start on Connections tab
        # Docker state
        self._docker_containers: list[DetectedContainer] = []
        self._docker_status_message: str | None = None
        self._loading_docker = False
        # Azure state
        self._azure_account: AzureAccount | None = None
        self._azure_subscriptions: list[AzureSubscription] = []
        self._azure_servers: list[AzureSqlServer] = []
        self._azure_status: AzureStatus | None = None
        self._loading_azure = False
        self._current_subscription_index: int = 0

    def compose(self) -> ComposeResult:
        with Dialog(id="picker-dialog", title="Connect"):
            yield FilterInput(id="picker-filter")
            yield OptionList(id="picker-list")

    def on_mount(self) -> None:
        """Load Docker containers and Azure resources when screen mounts."""
        self._update_dialog_title()
        self._rebuild_list()
        self._load_containers_async()
        self._load_azure_async()
        self._update_shortcuts()

    def _update_dialog_title(self) -> None:
        """Update dialog title to show current tab."""
        dialog = self.query_one("#picker-dialog", Dialog)
        if self._current_tab == self.TAB_CONNECTIONS:
            dialog.border_title = "[bold]Connections[/] │ [dim]Docker[/] │ [dim]Cloud[/]  [dim]<tab>[/]"
        elif self._current_tab == self.TAB_DOCKER:
            dialog.border_title = "[dim]Connections[/] │ [bold]Docker[/] │ [dim]Cloud[/]  [dim]<tab>[/]"
        else:
            dialog.border_title = "[dim]Connections[/] │ [dim]Docker[/] │ [bold]Cloud[/]  [dim]<tab>[/]"

    def _update_shortcuts(self) -> None:
        """Update dialog shortcuts based on current selection."""
        option = self._get_highlighted_option()
        show_save = False
        show_azure_account = False

        if option and option.id == "_azure_account":
            show_azure_account = True
        elif option and self._is_docker_option(option):
            container_id = str(option.id)[len(self.DOCKER_PREFIX):]
            container = self._get_container_by_id(container_id)
            if container and not self._is_container_saved(container):
                show_save = True
        elif option and self._is_azure_option(option):
            server_name, database, use_sql_auth = self._parse_azure_option_id(str(option.id))
            server = self._get_azure_server_by_name(server_name)
            if server and not self._is_azure_connection_saved(server, database, use_sql_auth):
                show_save = True

        if show_azure_account:
            shortcuts = [("Logout", "l"), ("Switch", "w")]
        else:
            shortcuts = [("Select", "enter")]
            if show_save:
                shortcuts.append(("Save", "s"))
            if self._current_tab == self.TAB_CONNECTIONS:
                shortcuts.append(("New", "n"))

        dialog = self.query_one("#picker-dialog", Dialog)
        subtitle = "\u00a0·\u00a0".join(
            f"{action}: [bold]<{key}>[/]" for action, key in shortcuts
        )
        dialog.border_subtitle = subtitle

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Update shortcuts when selection changes."""
        if event.option_list.id == "picker-list":
            self._update_shortcuts()

    def _load_containers_async(self) -> None:
        """Start async loading of Docker containers."""
        self._loading_docker = True
        self._rebuild_list()
        self.run_worker(self._detect_docker_worker, thread=True)

    def _detect_docker_worker(self) -> None:
        """Worker function to detect containers off-thread."""
        from ...services.docker_detector import detect_database_containers

        # Add a small delay for visual feedback if desired, or just run
        status, containers = detect_database_containers()
        self.app.call_from_thread(self._on_containers_loaded, status, containers)

    def _on_containers_loaded(
        self, status: DockerStatus, containers: list[DetectedContainer]
    ) -> None:
        """Callback when containers are loaded."""
        from ...services.docker_detector import DockerStatus

        self._loading_docker = False
        self._docker_containers = containers

        # Set status message based on Docker state
        if status == DockerStatus.NOT_INSTALLED:
            self._docker_status_message = "(Docker not detected)"
        elif status == DockerStatus.NOT_RUNNING:
            self._docker_status_message = "(Docker not running)"
        elif status == DockerStatus.NOT_ACCESSIBLE:
            self._docker_status_message = "(Docker not accessible)"
        elif status == DockerStatus.AVAILABLE and not containers:
            self._docker_status_message = "(no database containers found)"
        else:
            self._docker_status_message = None

        self._rebuild_list()
        self._update_shortcuts()

    def _load_azure_async(self) -> None:
        """Start async loading of Azure resources."""
        self._loading_azure = True
        self._rebuild_list()
        self.run_worker(self._detect_azure_worker, thread=True)

    def _detect_azure_worker(self) -> None:
        """Worker function to detect Azure resources off-thread."""
        from ...services.cloud_detector import (
            AzureStatus,
            cache_subscriptions_and_servers,
            detect_azure_sql_resources,
            get_azure_account,
            get_azure_subscriptions,
            get_cached_subscriptions,
        )

        try:
            # Get current account info
            account = get_azure_account()

            # Try cache first for subscriptions
            subscriptions = get_cached_subscriptions()
            if subscriptions is None:
                subscriptions = get_azure_subscriptions()

            # Get default subscription ID for caching
            default_sub_id = ""
            for sub in subscriptions:
                if sub.is_default:
                    default_sub_id = sub.id
                    break

            # Detect servers (uses cache internally if available)
            status, servers = detect_azure_sql_resources(default_sub_id, use_cache=True)

            # Cache results for next time
            if subscriptions and default_sub_id:
                cache_subscriptions_and_servers(subscriptions, servers, default_sub_id)

            self.app.call_from_thread(self._on_azure_loaded, status, account, subscriptions, servers)
        except Exception as e:
            self.app.call_from_thread(self._on_azure_error, str(e))

    def _on_azure_loaded(
        self,
        status: AzureStatus,
        account: AzureAccount | None,
        subscriptions: list[AzureSubscription],
        servers: list[AzureSqlServer],
    ) -> None:
        """Callback when Azure resources are loaded."""
        self._loading_azure = False
        self._azure_status = status
        self._azure_account = account
        self._azure_subscriptions = subscriptions
        self._azure_servers = servers

        # Find the default subscription index
        for i, sub in enumerate(subscriptions):
            if sub.is_default:
                self._current_subscription_index = i
                break

        self._rebuild_list()
        self._update_shortcuts()

        # Auto-load databases for all servers in parallel
        self._auto_load_all_databases()

    def _on_azure_error(self, error: str) -> None:
        """Callback when Azure detection fails."""
        from ...services.cloud_detector import AzureStatus

        self._loading_azure = False
        self._azure_status = AzureStatus.ERROR
        self._rebuild_list()
        self.notify(f"Azure error: {error}", severity="error")

    def _load_azure_for_subscription(self, subscription_id: str) -> None:
        """Load Azure resources for a specific subscription."""
        self._loading_azure = True
        self._azure_servers = []
        self._rebuild_list()
        self.run_worker(
            lambda: self._detect_azure_subscription_worker(subscription_id),
            thread=True,
        )

    def _detect_azure_subscription_worker(self, subscription_id: str) -> None:
        """Worker function to detect Azure resources for specific subscription."""
        from ...services.cloud_detector import (
            cache_subscriptions_and_servers,
            detect_azure_sql_resources,
        )

        try:
            status, servers = detect_azure_sql_resources(subscription_id, use_cache=True)

            # Cache servers for this subscription
            if self._azure_subscriptions:
                cache_subscriptions_and_servers(
                    self._azure_subscriptions, servers, subscription_id
                )

            self.app.call_from_thread(self._on_azure_subscription_loaded, status, servers)
        except Exception as e:
            self.app.call_from_thread(self._on_azure_error, str(e))

    def _on_azure_subscription_loaded(
        self, status: AzureStatus, servers: list[AzureSqlServer]
    ) -> None:
        """Callback when Azure resources for a subscription are loaded."""
        self._loading_azure = False
        self._azure_status = status
        self._azure_servers = servers

        self._rebuild_list()
        # Keep current subscription selected after switch
        self._select_option_by_id(f"_azure_sub_{self._current_subscription_index}")
        self._update_shortcuts()

        # Auto-load databases for all servers in parallel
        self._auto_load_all_databases()

    def _is_container_saved(self, container: DetectedContainer) -> bool:
        """Check if a Docker container matches a saved connection."""
        for conn in self.connections:
            # Match by host:port and db_type
            if (
                conn.db_type == container.db_type
                and conn.server in ("localhost", "127.0.0.1", container.host)
                and conn.port == str(container.port)
            ):
                return True
            # Also match by name
            if conn.name == container.container_name:
                return True
        return False

    def _build_options(self, pattern: str) -> list[Option]:
        """Build option list with fuzzy highlighting and sections based on current tab."""
        if self._current_tab == self.TAB_CONNECTIONS:
            return self._build_connections_options(pattern)
        elif self._current_tab == self.TAB_DOCKER:
            return self._build_docker_options(pattern)
        else:
            return self._build_cloud_options(pattern)

    def _build_connections_options(self, pattern: str) -> list[Option]:
        """Build options for the Connections tab (Saved connections only)."""
        options: list[Option] = []

        # Filter saved connections
        saved_options = []
        for conn in self.connections:
            matches, indices = fuzzy_match(pattern, conn.name)
            if matches or not pattern:
                display = highlight_matches(conn.name, indices)
                db_type = conn.db_type.upper() if conn.db_type else "DB"
                info = get_connection_display_info(conn)
                # Add source indicator emoji
                source_emoji = ""
                if conn.source == "azure":
                    source_emoji = ""
                elif conn.source == "docker":
                    source_emoji = "🐳 "
                saved_options.append(
                    Option(f"{source_emoji}{display} [{db_type}] [dim]({info})[/]", id=conn.name)
                )

        # Add Saved section
        options.append(Option("[bold]Saved[/]", id="_header_saved", disabled=True))

        if saved_options:
            options.extend(saved_options)
        else:
            options.append(
                Option("[dim](no saved connections)[/]", id="_empty_saved", disabled=True)
            )

        return options

    def _build_docker_options(self, pattern: str) -> list[Option]:
        """Build options for the Docker tab (containers only)."""
        options: list[Option] = []

        # Filter saved Docker connections
        saved_options = []
        for conn in self.connections:
            if conn.source != "docker":
                continue
            matches, indices = fuzzy_match(pattern, conn.name)
            if matches or not pattern:
                display = highlight_matches(conn.name, indices)
                db_type = conn.db_type.upper() if conn.db_type else "DB"
                info = get_connection_display_info(conn)
                saved_options.append(
                    Option(f"🐳 {display} [{db_type}] [dim]({info})[/]", id=conn.name)
                )

        # Filter Docker containers - separate running and exited, exclude saved ones
        running_options = []
        exited_options = []
        for container in self._docker_containers:
            is_saved = self._is_container_saved(container)
            if is_saved:
                continue  # Skip saved containers, they're in the Saved section

            matches, indices = fuzzy_match(pattern, container.container_name)
            if matches or not pattern:
                display = highlight_matches(container.container_name, indices)
                db_label = container.get_display_name().split("(")[-1].rstrip(")")
                port_info = f":{container.port}" if container.port else ""

                if container.is_running:
                    if container.connectable:
                        running_options.append(
                            Option(
                                f"🐳 {display} [{db_label}] [dim](localhost{port_info})[/]",
                                id=f"{self.DOCKER_PREFIX}{container.container_id}",
                            )
                        )
                    else:
                        running_options.append(
                            Option(
                                f"🐳 {display} [{db_label}] [dim](not exposed)[/]",
                                id=f"{self.DOCKER_PREFIX}{container.container_id}",
                                disabled=True,
                            )
                        )
                else:
                    # Exited containers - dim styling, selectable but not connectable
                    exited_options.append(
                        Option(
                            f"[dim]🐳 {display} [{db_label}] (Stopped)[/]",
                            id=f"{self.DOCKER_PREFIX}{container.container_id}",
                        )
                    )

        # Add Saved section
        options.append(Option("[bold]Saved[/]", id="_header_docker_saved", disabled=True))

        if saved_options:
            options.extend(saved_options)
        else:
            options.append(
                Option("[dim](no saved Docker connections)[/]", id="_empty_docker_saved", disabled=True)
            )

        # Add Running section
        options.append(Option("", id="_spacer1", disabled=True))
        options.append(Option("[bold]Running[/]", id="_header_docker", disabled=True))

        if self._loading_docker:
            options.append(Option("[dim italic]Loading...[/]", id="_docker_loading", disabled=True))
        elif running_options:
            options.extend(running_options)
        elif self._docker_status_message:
            options.append(
                Option(f"[dim]{self._docker_status_message}[/]", id="_docker_status", disabled=True)
            )
        else:
            options.append(
                Option("[dim](no running containers)[/]", id="_docker_empty", disabled=True)
            )

        # Add Stopped section (exited containers)
        if exited_options:
            options.append(Option("", id="_spacer2", disabled=True))
            options.append(Option("[bold]Stopped[/]", id="_header_docker_unavailable", disabled=True))
            options.extend(exited_options)

        return options

    def _build_cloud_options(self, pattern: str) -> list[Option]:
        """Build options for the Cloud tab (Azure, AWS, GCP)."""
        from ...services.cloud_detector import AzureStatus

        options: list[Option] = []

        # Azure section
        options.append(Option("[bold]Azure[/]", id="_header_azure", disabled=True))

        # Handle different Azure CLI states
        if self._loading_azure:
            options.append(Option("[dim italic]  Loading...[/]", id="_azure_loading", disabled=True))
        elif self._azure_status == AzureStatus.CLI_NOT_INSTALLED:
            options.append(
                Option(
                    "  [dim](Azure CLI not installed)[/]",
                    id="_azure_cli_missing",
                    disabled=True,
                )
            )
        elif self._azure_status == AzureStatus.NOT_LOGGED_IN:
            options.append(
                Option(
                    "  🔑 Login to Azure...",
                    id="_azure_login",
                )
            )
        elif self._azure_status == AzureStatus.ERROR:
            options.append(
                Option(
                    "  [red]⚠ Azure CLI error[/]",
                    id="_azure_error",
                    disabled=True,
                )
            )
            options.append(
                Option(
                    "    [dim]Try running 'az account show' in terminal[/]",
                    id="_azure_error_hint",
                    disabled=True,
                )
            )
        elif self._azure_subscriptions:
            # Show account info as child of Azure
            if self._azure_account:
                account_display = self._azure_account.username
                if len(account_display) > 40:
                    account_display = account_display[:37] + "..."
                options.append(
                    Option(
                        f"  👤 {account_display}",
                        id="_azure_account",
                    )
                )

            # Show subscriptions as children of account (indented)
            for i, sub in enumerate(self._azure_subscriptions):
                sub_display = f"{sub.name[:40]}..." if len(sub.name) > 40 else sub.name
                is_active = i == self._current_subscription_index
                if is_active:
                    options.append(
                        Option(
                            f"    [green]🔑 ★ {sub_display}[/]",
                            id=f"_azure_sub_{i}",
                        )
                    )
                else:
                    options.append(
                        Option(
                            f"    [dim]🔑 {sub_display}[/]",
                            id=f"_azure_sub_{i}",
                        )
                    )

            # Show servers under active subscription (hierarchical)
            azure_options = []
            for server in self._azure_servers:
                matches, indices = fuzzy_match(pattern, server.name)
                if matches or not pattern:
                    display = highlight_matches(server.name, indices)

                    # Check if databases are loaded (from server object or being loaded)
                    server_key = f"{server.name}:{server.resource_group}"
                    is_loading = server_key in getattr(self, "_loading_databases", set())

                    if is_loading:
                        # Show server with loading indicator
                        azure_options.append(
                            Option(
                                f"      {display} [dim italic]loading...[/]",
                                id=f"_azure_server_loading_{server.name}",
                                disabled=True,
                            )
                        )
                    elif server.databases:
                        # Show server as header (collapsed indicator)
                        azure_options.append(
                            Option(
                                f"      {display}",
                                id=f"_azure_server_{server.name}",
                                disabled=True,
                            )
                        )
                        # Show databases indented under server
                        for db in server.databases:
                            db_matches, db_indices = fuzzy_match(pattern, db)
                            if db_matches or not pattern:
                                db_display = highlight_matches(db, db_indices) if pattern else db
                                # Check saved status for each auth type
                                ad_saved = self._is_azure_connection_saved(server, db, False)
                                sql_saved = self._is_azure_connection_saved(server, db, True)
                                # Entra ID (AD) auth option - dim if saved
                                if ad_saved:
                                    azure_options.append(
                                        Option(
                                            f"        [dim]📁 {db_display} Entra ✓[/]",
                                            id=f"{self.AZURE_PREFIX}{server.name}:{db}:ad",
                                        )
                                    )
                                else:
                                    azure_options.append(
                                        Option(
                                            f"        📁 {db_display} [dim]Entra[/]",
                                            id=f"{self.AZURE_PREFIX}{server.name}:{db}:ad",
                                        )
                                    )
                                # SQL Server auth option - dim if saved
                                if sql_saved:
                                    azure_options.append(
                                        Option(
                                            f"        [dim]📁 {db_display} SQL Auth ✓[/]",
                                            id=f"{self.AZURE_PREFIX}{server.name}:{db}:sql",
                                        )
                                    )
                                else:
                                    azure_options.append(
                                        Option(
                                            f"        📁 {db_display} [dim]SQL Auth[/]",
                                            id=f"{self.AZURE_PREFIX}{server.name}:{db}:sql",
                                        )
                                    )
                    else:
                        # No databases loaded yet - will auto-load
                        azure_options.append(
                            Option(
                                f"      {display} [dim](no databases)[/]",
                                id=f"_azure_server_empty_{server.name}",
                                disabled=True,
                            )
                        )

            if azure_options:
                options.extend(azure_options)
            else:
                options.append(
                    Option("[dim]        (no SQL servers in this subscription)[/]", id="_azure_no_servers", disabled=True)
                )
        else:
            # Logged in but no subscriptions - show account with option to switch
            if self._azure_account:
                account_display = self._azure_account.username
                if len(account_display) > 40:
                    account_display = account_display[:37] + "..."
                options.append(
                    Option(
                        f"  👤 {account_display}",
                        id="_azure_account",
                    )
                )
            options.append(
                Option(
                    "    [yellow]⚠ No subscriptions found[/]",
                    id="_azure_no_subs",
                    disabled=True,
                )
            )

        # AWS section (placeholder)
        options.append(Option("", id="_spacer_aws", disabled=True))
        options.append(Option("[bold]AWS[/]", id="_header_aws", disabled=True))
        options.append(Option("[dim]  (coming soon)[/]", id="_aws_empty", disabled=True))

        # GCP section (placeholder)
        options.append(Option("", id="_spacer_gcp", disabled=True))
        options.append(Option("[bold]GCP[/]", id="_header_gcp", disabled=True))
        options.append(Option("[dim]  (coming soon)[/]", id="_gcp_empty", disabled=True))

        return options

    def _rebuild_list(self) -> None:
        """Rebuild the option list."""
        try:
            option_list = self.query_one("#picker-list", OptionList)
        except Exception:
            return

        option_list.clear_options()
        options = self._build_options(self.search_text)

        for opt in options:
            option_list.add_option(opt)

        # Find first selectable option
        self._select_first_selectable()

    def _select_first_selectable(self) -> None:
        """Select the first non-disabled option."""
        try:
            option_list = self.query_one("#picker-list", OptionList)
        except Exception:
            return

        for i in range(option_list.option_count):
            option = option_list.get_option_at_index(i)
            if option and not option.disabled:
                option_list.highlighted = i
                return

    def _update_list(self) -> None:
        """Update the option list based on search."""
        self._rebuild_list()

    def on_key(self, event: Key) -> None:
        """Handle key presses for fuzzy search when filter is active."""
        if not self._filter_active:
            return

        key = event.key

        # Handle backspace
        if key == "backspace":
            if self.search_text:
                self.search_text = self.search_text[:-1]
                self._update_filter_display()
                self._update_list()
            else:
                # Close filter when backspacing with no text
                self._close_filter()
            event.prevent_default()
            event.stop()
            return

        # Handle printable characters
        if event.character and event.character.isprintable():
            # Don't capture "/" when filter is already active (it's a search char)
            self.search_text += event.character
            self._update_filter_display()
            self._update_list()
            event.prevent_default()
            event.stop()

    def action_backspace(self) -> None:
        """Remove last character from search (only if filter not active, otherwise on_key handles it)."""
        if not self._filter_active:
            return
        # Handled in on_key when filter is active
        pass

    def action_open_filter(self) -> None:
        """Open the search filter."""
        self._filter_active = True
        self.search_text = ""
        filter_input = self.query_one("#picker-filter", FilterInput)
        filter_input.show()
        self._update_filter_display()

    def _close_filter(self) -> None:
        """Close the search filter and clear search."""
        self._filter_active = False
        self.search_text = ""
        filter_input = self.query_one("#picker-filter", FilterInput)
        filter_input.hide()
        self._update_list()

    def _update_filter_display(self) -> None:
        """Update the filter input display."""
        filter_input = self.query_one("#picker-filter", FilterInput)
        # Count total and matching options
        total = len(self.connections) + len(self._docker_containers)
        if self.search_text:
            match_count = self._count_matches()
            filter_input.set_filter(self.search_text, match_count, total)
        else:
            filter_input.set_filter("", 0, total)

    def _count_matches(self) -> int:
        """Count the number of matching options."""
        count = 0
        pattern = self.search_text
        for conn in self.connections:
            matches, _ = fuzzy_match(pattern, conn.name)
            if matches:
                count += 1
        for container in self._docker_containers:
            matches, _ = fuzzy_match(pattern, container.container_name)
            if matches:
                count += 1
        return count

    def action_cancel_or_close_filter(self) -> None:
        """Close filter if active, otherwise cancel and close the picker."""
        if self._filter_active:
            self._close_filter()
        else:
            self.dismiss(None)

    def action_move_up(self) -> None:
        """Move selection up, skipping disabled options."""
        try:
            option_list = self.query_one("#picker-list", OptionList)
            if option_list.highlighted is None:
                return

            current = option_list.highlighted
            # Find previous non-disabled option
            for i in range(current - 1, -1, -1):
                option = option_list.get_option_at_index(i)
                if option and not option.disabled:
                    option_list.highlighted = i
                    return
        except Exception:
            pass

    def action_move_down(self) -> None:
        """Move selection down, skipping disabled options."""
        try:
            option_list = self.query_one("#picker-list", OptionList)
            if option_list.highlighted is None:
                return

            current = option_list.highlighted
            count = option_list.option_count
            # Find next non-disabled option
            for i in range(current + 1, count):
                option = option_list.get_option_at_index(i)
                if option and not option.disabled:
                    option_list.highlighted = i
                    return
        except Exception:
            pass

    def _get_highlighted_option(self) -> Option | None:
        """Get the currently highlighted option."""
        try:
            option_list = self.query_one("#picker-list", OptionList)
            highlighted = option_list.highlighted
            if highlighted is not None:
                return option_list.get_option_at_index(highlighted)
        except Exception:
            pass
        return None

    def _is_docker_option(self, option: Option) -> bool:
        """Check if an option represents a Docker container."""
        return option.id is not None and str(option.id).startswith(self.DOCKER_PREFIX)

    def _is_azure_option(self, option: Option) -> bool:
        """Check if an option represents an Azure resource."""
        return option.id is not None and str(option.id).startswith(self.AZURE_PREFIX)

    def _get_azure_server_by_name(self, server_name: str) -> AzureSqlServer | None:
        """Find an Azure server by its name."""
        for server in self._azure_servers:
            if server.name == server_name:
                return server
        return None

    def _parse_azure_option_id(self, option_id: str) -> tuple[str, str | None, bool]:
        """Parse Azure option ID into (server_name, database_name, use_sql_auth)."""
        # Format: azure:servername:dbname:ad or azure:servername:dbname:sql
        parts = option_id[len(self.AZURE_PREFIX):].split(":")
        server_name = parts[0]
        database = parts[1] if len(parts) > 1 and parts[1] else None
        use_sql_auth = parts[2] == "sql" if len(parts) > 2 else False
        return server_name, database, use_sql_auth

    def _get_container_by_id(self, container_id: str) -> DetectedContainer | None:
        """Find a container by its ID."""
        for container in self._docker_containers:
            if container.container_id == container_id:
                return container
        return None

    def action_select(self) -> None:
        """Select the highlighted option."""
        option = self._get_highlighted_option()
        if not option or option.disabled:
            return

        # Subscription selector - activate the selected subscription
        if option.id and str(option.id).startswith("_azure_sub_"):
            sub_index = int(str(option.id).replace("_azure_sub_", ""))
            self._activate_subscription(sub_index)
            return

        # Azure login action
        if option.id == "_azure_login":
            self._start_azure_login()
            return

        # Azure account - use l/w keybindings, enter does nothing
        if option.id == "_azure_account":
            return

        # Load databases for a server
        if option.id and str(option.id).startswith("_azure_load_dbs_"):
            server_name = str(option.id).replace("_azure_load_dbs_", "")
            self._load_databases_for_server(server_name)
            return

        if self._is_docker_option(option):
            # Docker container - connect directly
            container_id = str(option.id)[len(self.DOCKER_PREFIX) :]
            container = self._get_container_by_id(container_id)
            if container:
                if not container.is_running:
                    self.notify("Container is not running", severity="warning")
                    return
                self.dismiss(DockerConnectionResult(container=container, action="connect"))
        elif self._is_azure_option(option):
            # Azure resource - connect with chosen auth method
            server_name, database, use_sql_auth = self._parse_azure_option_id(str(option.id))
            server = self._get_azure_server_by_name(server_name)
            if server:
                self.dismiss(AzureConnectionResult(server=server, database=database, use_sql_auth=use_sql_auth))
        else:
            # Saved connection
            self.dismiss(option.id)

    def _activate_subscription(self, index: int) -> None:
        """Activate a subscription by index and load its servers."""
        if index == self._current_subscription_index:
            return  # Already active
        if index < 0 or index >= len(self._azure_subscriptions):
            return

        self._current_subscription_index = index
        current_sub = self._azure_subscriptions[index]
        self.notify(f"Loading {current_sub.name}...")
        self._load_azure_for_subscription(current_sub.id)

    def _auto_load_all_databases(self) -> None:
        """Automatically load databases for all servers in parallel."""
        if not self._azure_servers:
            return

        # Initialize loading set
        if not hasattr(self, "_loading_databases"):
            self._loading_databases: set[str] = set()

        # Start loading for each server that doesn't have databases yet
        for server in self._azure_servers:
            if server.databases:
                continue  # Already has databases (from cache)

            server_key = f"{server.name}:{server.resource_group}"
            if server_key in self._loading_databases:
                continue  # Already loading

            self._loading_databases.add(server_key)

            # Start worker for this server (runs in parallel)
            self.run_worker(
                lambda s=server: self._load_databases_worker(s),
                thread=True,
            )

        # Rebuild list to show loading indicators
        if self._loading_databases:
            self._rebuild_list()

    def _load_databases_for_server(self, server_name: str) -> None:
        """Load databases for a specific server (manual trigger)."""
        server = self._get_azure_server_by_name(server_name)
        if not server:
            return

        # Track loading state
        if not hasattr(self, "_loading_databases"):
            self._loading_databases: set[str] = set()

        server_key = f"{server.name}:{server.resource_group}"
        if server_key in self._loading_databases:
            return  # Already loading

        self._loading_databases.add(server_key)
        self._rebuild_list()

        self.run_worker(
            lambda: self._load_databases_worker(server),
            thread=True,
        )

    def _load_databases_worker(self, server: AzureSqlServer) -> None:
        """Worker to load databases for a server."""
        from ...services.cloud_detector import load_databases_for_server

        databases = load_databases_for_server(server, use_cache=True)
        self.app.call_from_thread(self._on_databases_loaded, server, databases)

    def _on_databases_loaded(self, server: AzureSqlServer, databases: list[str]) -> None:
        """Callback when databases are loaded for a server."""
        server_key = f"{server.name}:{server.resource_group}"

        # Remove from loading set
        if hasattr(self, "_loading_databases"):
            self._loading_databases.discard(server_key)

        # Update server's databases
        server.databases = databases

        self._rebuild_list()

        # Select the first database option for this server
        if databases:
            self._select_option_by_id(f"{self.AZURE_PREFIX}{server.name}:{databases[0]}:ad")
        else:
            self.notify(f"No databases found on {server.name}", severity="warning")

    def _start_azure_login(self) -> None:
        """Start Azure CLI login process."""
        self.notify("Opening browser for Azure login...")
        self._loading_azure = True
        self._rebuild_list()
        self.run_worker(self._azure_login_worker, thread=True)

    def _azure_login_worker(self) -> None:
        """Worker to run az login."""
        import subprocess

        try:
            # az login opens browser - capture output to avoid TUI conflicts
            result = subprocess.run(
                ["az", "login"],
                capture_output=True,
                timeout=300,  # 5 min timeout for login
            )
            if result.returncode == 0:
                self.app.call_from_thread(self._on_azure_login_complete, True)
            else:
                error = result.stderr.decode() if result.stderr else "Login failed"
                self.app.call_from_thread(self._on_azure_login_error, error)
        except subprocess.TimeoutExpired:
            self.app.call_from_thread(self._on_azure_login_error, "Login timed out")
        except Exception as e:
            self.app.call_from_thread(self._on_azure_login_error, str(e))

    def _on_azure_login_complete(self, success: bool) -> None:
        """Callback when Azure login completes."""
        if success:
            self.notify("Azure login successful! Loading resources...")
            self._load_azure_async()

    def _on_azure_login_error(self, error: str) -> None:
        """Callback when Azure login fails."""
        self._loading_azure = False
        self._rebuild_list()
        # Truncate long error messages
        if len(error) > 100:
            error = error[:100] + "..."
        self.notify(f"Azure login failed: {error}", severity="error")

    def action_azure_logout(self) -> None:
        """Logout from Azure (only when account is highlighted)."""
        option = self._get_highlighted_option()
        if option and option.id == "_azure_account":
            self._start_azure_logout()

    def action_azure_switch(self) -> None:
        """Switch Azure account (only when account is highlighted)."""
        option = self._get_highlighted_option()
        if option and option.id == "_azure_account":
            self._start_azure_login()

    def _start_azure_logout(self) -> None:
        """Start Azure CLI logout process."""
        self.notify("Logging out from Azure...")
        self._loading_azure = True
        self._rebuild_list()
        self.run_worker(self._azure_logout_worker, thread=True)

    def _azure_logout_worker(self) -> None:
        """Worker to run az logout."""
        from ...services.cloud_detector import azure_logout

        success = azure_logout()
        self.app.call_from_thread(self._on_azure_logout_complete, success)

    def _on_azure_logout_complete(self, success: bool) -> None:
        """Callback when Azure logout completes."""
        self._loading_azure = False
        self._azure_account = None
        self._azure_subscriptions = []
        self._azure_servers = []

        if success:
            from ...services.cloud_detector import AzureStatus

            self._azure_status = AzureStatus.NOT_LOGGED_IN
            self.notify("Logged out from Azure")
        else:
            self.notify("Failed to logout from Azure", severity="warning")

        self._rebuild_list()

    def action_switch_tab(self) -> None:
        """Switch between Connections, Docker and Cloud tabs."""
        if self._current_tab == self.TAB_CONNECTIONS:
            self._current_tab = self.TAB_DOCKER
        elif self._current_tab == self.TAB_DOCKER:
            self._current_tab = self.TAB_CLOUD
        else:
            self._current_tab = self.TAB_CONNECTIONS

        self._update_dialog_title()
        self._rebuild_list()
        self._update_shortcuts()

    def action_save_docker(self) -> None:
        """Save the selected Docker container or Azure resource as a connection."""
        option = self._get_highlighted_option()
        if not option or option.disabled:
            return

        if self._is_docker_option(option):
            container_id = str(option.id)[len(self.DOCKER_PREFIX) :]
            container = self._get_container_by_id(container_id)
            if container:
                # Check if already saved
                if self._is_container_saved(container):
                    self.notify("Container already saved", severity="warning")
                    return
                # Save the container as a connection
                self._save_container(container)
        elif self._is_azure_option(option):
            server_name, database, use_sql_auth = self._parse_azure_option_id(str(option.id))
            server = self._get_azure_server_by_name(server_name)
            if server:
                # Check if already saved
                if self._is_azure_connection_saved(server, database, use_sql_auth):
                    self.notify("Connection already saved", severity="warning")
                    return
                # Save the Azure connection
                self._save_azure_connection(server, database, use_sql_auth)
        else:
            # For saved connections, 's' does nothing special
            pass

    def _save_container(self, container: DetectedContainer) -> None:
        """Save a Docker container as a connection without closing the modal."""
        from ...config import save_connections
        from ...services.docker_detector import container_to_connection_config

        config = container_to_connection_config(container)

        # Generate unique name if needed
        existing_names = {c.name for c in self.connections}
        base_name = config.name
        new_name = base_name
        counter = 2
        while new_name in existing_names:
            new_name = f"{base_name}-{counter}"
            counter += 1
        config.name = new_name

        # Add to connections list
        self.connections.append(config)

        # Persist (check for mock mode via app)
        try:
            if getattr(self.app, "_mock_profile", None):
                self.notify(f"Mock mode: '{config.name}' not persisted")
            else:
                save_connections(self.connections)
                self.notify(f"Saved '{config.name}'")
        except Exception as e:
            self.notify(f"Failed to save: {e}", severity="error")
            return

        # Remember the current container ID to restore cursor position
        current_option_id = f"{self.DOCKER_PREFIX}{container.container_id}"

        # Refresh the list to update saved indicators
        self._rebuild_list()

        # Refresh the app's explorer tree to show new connection
        if hasattr(self.app, "refresh_tree"):
            self.app.refresh_tree()

        # Restore cursor to the same container
        self._select_option_by_id(current_option_id)

    def _is_azure_connection_saved(
        self, server: AzureSqlServer, database: str | None, use_sql_auth: bool
    ) -> bool:
        """Check if an Azure connection matches a saved connection."""
        auth_type = "sql" if use_sql_auth else "ad_default"
        for conn in self.connections:
            if (
                conn.db_type == "mssql"
                and conn.server == server.fqdn
                and conn.database == (database or "master")
                and conn.options.get("auth_type") == auth_type
            ):
                return True
        return False

    def _save_azure_connection(
        self, server: AzureSqlServer, database: str | None, use_sql_auth: bool
    ) -> None:
        """Save an Azure connection without closing the modal."""
        from ...config import save_connections
        from ...services.cloud_detector import azure_server_to_connection_config

        config = azure_server_to_connection_config(server, database, use_sql_auth)

        # Generate unique name if needed
        existing_names = {c.name for c in self.connections}
        base_name = config.name
        new_name = base_name
        counter = 2
        while new_name in existing_names:
            new_name = f"{base_name}-{counter}"
            counter += 1
        config.name = new_name

        # Add to connections list
        self.connections.append(config)

        # Persist (check for mock mode via app)
        try:
            if getattr(self.app, "_mock_profile", None):
                self.notify(f"Mock mode: '{config.name}' not persisted")
            else:
                save_connections(self.connections)
                self.notify(f"Saved '{config.name}'")
        except Exception as e:
            self.notify(f"Failed to save: {e}", severity="error")
            return

        # Remember current option to restore cursor
        auth_suffix = "sql" if use_sql_auth else "ad"
        current_option_id = f"{self.AZURE_PREFIX}{server.name}:{database or ''}:{auth_suffix}"

        # Refresh the list to update saved indicators
        self._rebuild_list()

        # Refresh the app's explorer tree to show new connection
        if hasattr(self.app, "refresh_tree"):
            self.app.refresh_tree()

        # Restore cursor position
        self._select_option_by_id(current_option_id)

    def _select_option_by_id(self, option_id: str) -> None:
        """Select an option by its ID."""
        try:
            option_list = self.query_one("#picker-list", OptionList)
            for i in range(option_list.option_count):
                option = option_list.get_option_at_index(i)
                if option and option.id == option_id:
                    option_list.highlighted = i
                    return
        except Exception:
            pass

    def action_new_connection(self) -> None:
        """Open new connection dialog."""
        self.dismiss("__new_connection__")

    def action_refresh(self) -> None:
        """Refresh Docker containers and Azure resources (clears cache)."""
        from ...services.cloud_detector import clear_azure_cache

        # Clear the Azure cache to force fresh data
        clear_azure_cache()

        self._load_containers_async()
        self._load_azure_async()
        self.notify("Refreshing...")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle option selection via click."""
        if event.option_list.id == "picker-list":
            option = event.option
            if option and not option.disabled:
                # Subscription selector - activate the selected subscription
                if option.id and str(option.id).startswith("_azure_sub_"):
                    sub_index = int(str(option.id).replace("_azure_sub_", ""))
                    self._activate_subscription(sub_index)
                    return

                # Azure login action
                if option.id == "_azure_login":
                    self._start_azure_login()
                    return

                # Azure account - use l/w keybindings, click does nothing
                if option.id == "_azure_account":
                    return

                # Load databases for a server
                if option.id and str(option.id).startswith("_azure_load_dbs_"):
                    server_name = str(option.id).replace("_azure_load_dbs_", "")
                    self._load_databases_for_server(server_name)
                    return

                if self._is_docker_option(option):
                    container_id = str(option.id)[len(self.DOCKER_PREFIX) :]
                    container = self._get_container_by_id(container_id)
                    if container:
                        self.dismiss(DockerConnectionResult(container=container, action="connect"))
                elif self._is_azure_option(option):
                    server_name, database, use_sql_auth = self._parse_azure_option_id(str(option.id))
                    server = self._get_azure_server_by_name(server_name)
                    if server:
                        self.dismiss(AzureConnectionResult(server=server, database=database, use_sql_auth=use_sql_auth))
                else:
                    self.dismiss(option.id)
