"""Connection picker screen with fuzzy search and Docker/Cloud detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import OptionList, Tree
from textual.widgets.option_list import Option
from textual.widgets.tree import TreeNode

from ...db.providers import get_connection_display_info
from ...services.cloud import ProviderState, ProviderStatus, get_providers
from ...utils import fuzzy_match, highlight_matches
from ...widgets import Dialog, FilterInput

if TYPE_CHECKING:
    from ...config import ConnectionConfig
    from ...services.cloud import CloudProvider
    from ...services.cloud_detector import AzureSqlServer
    from ...services.docker_detector import DetectedContainer


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


@dataclass
class CloudConnectionResult:
    """Result when selecting a cloud resource (AWS, GCP, etc.)."""

    config: ConnectionConfig
    provider_id: str  # "aws", "gcp", etc.

    def get_result_kind(self) -> str:
        return "cloud"


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

    #cloud-tree {
        height: 20;
        scrollbar-size: 1 1;
        display: none;
    }

    #cloud-tree.visible {
        display: block;
    }

    #picker-list.hidden {
        display: none;
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
        # Cloud provider states
        self._cloud_providers: list[CloudProvider] = get_providers()
        self._cloud_states: dict[str, ProviderState] = {
            p.id: ProviderState() for p in self._cloud_providers
        }

    def compose(self) -> ComposeResult:
        with Dialog(id="picker-dialog", title="Connect"):
            yield FilterInput(id="picker-filter")
            yield OptionList(id="picker-list")
            yield Tree("Cloud", id="cloud-tree")

    def on_mount(self) -> None:
        """Load Docker containers and cloud resources when screen mounts."""
        self._update_dialog_title()
        self._rebuild_list()
        self._load_containers_async()
        self._load_cloud_providers_async()
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
        show_save = False
        provider_shortcuts: list[tuple[str, str]] = []

        # Handle cloud tab with tree widget
        if self._current_tab == self.TAB_CLOUD:
            tree_node = self._get_highlighted_tree_node()
            if tree_node and tree_node.data:
                data = tree_node.data
                node_type = data.get("type")
                provider_id = data.get("provider_id")

                # Account nodes get Logout/Switch shortcuts
                if node_type == "account":
                    provider_shortcuts = [("Logout", "l"), ("Switch", "w")]

                # Check if we can save this node
                elif node_type == "database" and provider_id == "azure":
                    server = data.get("server")
                    database = data.get("database")
                    auth_type = data.get("auth_type", "ad")
                    if server and database:
                        show_save = not self._is_azure_connection_saved(server, database, auth_type == "sql")

                elif node_type == "rds_instance" and provider_id == "aws":
                    instance = data.get("instance")
                    if instance:
                        show_save = not self._is_aws_rds_saved(instance)

                elif node_type == "redshift_cluster" and provider_id == "aws":
                    cluster = data.get("cluster")
                    if cluster:
                        show_save = not self._is_aws_redshift_saved(cluster)

                elif node_type == "cloud_sql_instance" and provider_id == "gcp":
                    instance = data.get("instance")
                    if instance:
                        show_save = not self._is_gcp_instance_saved(instance)
        else:
            # Handle option list (Connections and Docker tabs)
            option = self._get_highlighted_option()
            if option:
                option_id = str(option.id) if option.id else ""

                # Check cloud providers for custom shortcuts
                for provider in self._cloud_providers:
                    if provider.is_my_option(option_id):
                        state = self._cloud_states.get(provider.id, ProviderState())
                        provider_shortcuts = provider.get_shortcuts(option_id, state)
                        # Check if this option can be saved
                        if option_id.startswith(provider.prefix):
                            result = provider.handle_action(
                                "check_save", option_id, state, self.connections
                            )
                            if result.config and result.action != "none":
                                # Check if not already saved
                                show_save = not any(
                                    c.name == result.config.name or (
                                        c.server == result.config.server and
                                        c.database == result.config.database
                                    )
                                    for c in self.connections
                                )
                        break

                # Check Docker options
                if not provider_shortcuts and self._is_docker_option(option):
                    container_id = str(option.id)[len(self.DOCKER_PREFIX):]
                    container = self._get_container_by_id(container_id)
                    if container and not self._is_container_saved(container):
                        show_save = True

        if provider_shortcuts:
            shortcuts = provider_shortcuts
        else:
            shortcuts = [("Select", "enter")]
            if show_save:
                shortcuts.append(("Save", "s"))
            if self._current_tab == self.TAB_CONNECTIONS:
                shortcuts.append(("New", "n"))

        # Always show Refresh on Docker/Cloud tabs
        if self._current_tab in (self.TAB_DOCKER, self.TAB_CLOUD):
            shortcuts.append(("Refresh", "f"))

        dialog = self.query_one("#picker-dialog", Dialog)
        subtitle = "\u00a0·\u00a0".join(
            f"{action}: [bold]<{key}>[/]" for action, key in shortcuts
        )
        dialog.border_subtitle = subtitle

    def _get_highlighted_tree_node(self) -> TreeNode | None:
        """Get the currently highlighted tree node."""
        try:
            tree = self.query_one("#cloud-tree", Tree)
            return tree.cursor_node
        except Exception:
            pass
        return None

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

    def _load_cloud_providers_async(self) -> None:
        """Start async loading of all cloud providers."""
        # Set all providers to loading state
        for provider in self._cloud_providers:
            self._cloud_states[provider.id] = ProviderState(loading=True)

        self._rebuild_list()

        # Start discovery for each provider in parallel
        for provider in self._cloud_providers:
            self.run_worker(
                lambda p=provider: self._discover_provider_worker(p),
                thread=True,
            )

    def _discover_provider_worker(self, provider: CloudProvider) -> None:
        """Worker function to discover resources for a provider."""
        try:
            state = ProviderState(loading=True)
            new_state = provider.discover(state)
            self.app.call_from_thread(self._on_provider_loaded, provider.id, new_state)
        except Exception as e:
            self.app.call_from_thread(self._on_provider_error, provider.id, str(e))

    def _on_provider_loaded(self, provider_id: str, state: ProviderState) -> None:
        """Callback when a provider finishes discovery."""
        self._cloud_states[provider_id] = state
        self._rebuild_list()
        if self._current_tab == self.TAB_CLOUD:
            self._rebuild_cloud_tree()
        self._update_shortcuts()

        # Auto-load databases for Azure servers
        if provider_id == "azure":
            self._auto_load_all_databases()

    def _on_provider_error(self, provider_id: str, error: str) -> None:
        """Callback when provider discovery fails."""
        from ...services.cloud import ProviderStatus

        self._cloud_states[provider_id] = ProviderState(
            status=ProviderStatus.ERROR,
            loading=False,
            error=error,
        )
        self._rebuild_list()
        if self._current_tab == self.TAB_CLOUD:
            self._rebuild_cloud_tree()
        self.notify(f"Cloud error: {error}", severity="error")

    def _is_container_saved(self, container: DetectedContainer) -> bool:
        """Check if a Docker container matches a saved connection."""
        for conn in self.connections:
            # Match by name (container name saved as connection name)
            if conn.name == container.container_name:
                return True

            # Match by host:port and db_type
            if (
                conn.db_type == container.db_type
                and conn.server in ("localhost", "127.0.0.1", container.host)
                and conn.port == str(container.port)
            ):
                # If container has a known database, require it to match too
                # This allows multiple containers on the same port with different databases
                if container.database:
                    if conn.database == container.database:
                        return True
                else:
                    # No database info on container, match by host:port only
                    return True
        return False

    def _build_options(self, pattern: str) -> list[Option]:
        """Build option list with fuzzy highlighting and sections based on current tab."""
        if self._current_tab == self.TAB_CONNECTIONS:
            return self._build_connections_options(pattern)
        elif self._current_tab == self.TAB_DOCKER:
            return self._build_docker_options(pattern)
        else:
            # Cloud tab uses Tree widget instead of OptionList
            return []

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

        option_id = str(option.id) if option.id else ""

        # Check if a cloud provider handles this option
        for provider in self._cloud_providers:
            if provider.is_my_option(option_id):
                state = self._cloud_states.get(provider.id, ProviderState())
                result = provider.handle_action("select", option_id, state, self.connections)

                if result.action == "login":
                    self._start_provider_login(provider)
                    return
                elif result.action == "logout":
                    self._start_provider_logout(provider)
                    return
                elif result.action == "switch_subscription":
                    sub_index = result.metadata.get("subscription_index", 0)
                    self._activate_subscription(provider, sub_index)
                    return
                elif result.action == "connect" and result.config:
                    # Use Azure-specific result for Azure provider (has special handling)
                    if provider.id == "azure":
                        self.dismiss(AzureConnectionResult(
                            server=self._get_server_from_config(result.config, state),
                            database=result.config.database,
                            use_sql_auth=result.config.options.get("auth_type") == "sql",
                        ))
                    else:
                        # Generic cloud result for AWS, GCP, etc.
                        self.dismiss(CloudConnectionResult(
                            config=result.config,
                            provider_id=provider.id,
                        ))
                    return
                elif result.action == "none":
                    return
                return

        # Docker container
        if self._is_docker_option(option):
            container_id = str(option.id)[len(self.DOCKER_PREFIX):]
            container = self._get_container_by_id(container_id)
            if container:
                if not container.is_running:
                    self.notify("Container is not running", severity="warning")
                    return
                self.dismiss(DockerConnectionResult(container=container, action="connect"))
            return

        # Saved connection
        self.dismiss(option.id)

    def _get_server_from_config(self, config: ConnectionConfig, state: ProviderState) -> AzureSqlServer | None:
        """Get Azure server object from a config."""
        servers = state.extra.get("servers", [])
        for server in servers:
            if server.fqdn == config.server:
                return server
        return None

    def _activate_subscription(self, provider: CloudProvider, index: int) -> None:
        """Activate a subscription by index and load its servers."""
        state = self._cloud_states.get(provider.id, ProviderState())
        subscriptions = state.extra.get("subscriptions", [])
        current_index = state.extra.get("current_subscription_index", 0)

        if index == current_index:
            return  # Already active
        if index < 0 or index >= len(subscriptions):
            return

        # Update state with new subscription index
        current_sub = subscriptions[index]
        self.notify(f"Loading {current_sub.name}...")
        self._load_provider_for_subscription(provider, current_sub.id, index)

    def _auto_load_all_databases(self) -> None:
        """Automatically load databases for all Azure servers in parallel."""
        state = self._cloud_states.get("azure", ProviderState())
        servers = state.extra.get("servers", [])

        if not servers:
            return

        # Initialize loading set
        if not hasattr(self, "_loading_databases"):
            self._loading_databases: set[str] = set()

        # Start loading for each server that doesn't have databases yet
        for server in servers:
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

    def _get_azure_server_by_name(self, server_name: str) -> AzureSqlServer | None:
        """Find an Azure server by its name."""
        state = self._cloud_states.get("azure", ProviderState())
        servers = state.extra.get("servers", [])
        for server in servers:
            if server.name == server_name:
                return server
        return None

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
        if self._current_tab == self.TAB_CLOUD:
            self._rebuild_cloud_tree()

        # Select the first database option for this server
        if databases:
            self._select_option_by_id(f"{self.AZURE_PREFIX}{server.name}:{databases[0]}:ad")
        else:
            self.notify(f"No databases found on {server.name}", severity="warning")

    def _start_provider_login(self, provider: CloudProvider) -> None:
        """Start login process for a cloud provider."""
        self.notify(f"Opening browser for {provider.name} login...")
        self._cloud_states[provider.id] = ProviderState(loading=True)
        self._rebuild_list()
        self.run_worker(
            lambda: self._provider_login_worker(provider),
            thread=True,
        )

    def _provider_login_worker(self, provider: CloudProvider) -> None:
        """Worker to run provider login."""
        try:
            success = provider.login()
            self.app.call_from_thread(self._on_provider_login_complete, provider, success)
        except Exception as e:
            self.app.call_from_thread(self._on_provider_login_error, provider, str(e))

    def _on_provider_login_complete(self, provider: CloudProvider, success: bool) -> None:
        """Callback when provider login completes."""
        if success:
            self.notify(f"{provider.name} login successful! Loading resources...")
            # Re-run discovery for this provider
            self._cloud_states[provider.id] = ProviderState(loading=True)
            self._rebuild_list()
            if self._current_tab == self.TAB_CLOUD:
                self._rebuild_cloud_tree()
            self.run_worker(
                lambda: self._discover_provider_worker(provider),
                thread=True,
            )
        else:
            self._cloud_states[provider.id] = ProviderState(
                status=ProviderStatus.NOT_LOGGED_IN,
                loading=False,
            )
            self._rebuild_list()
            if self._current_tab == self.TAB_CLOUD:
                self._rebuild_cloud_tree()
            self.notify(f"{provider.name} login failed", severity="error")

    def _on_provider_login_error(self, provider: CloudProvider, error: str) -> None:
        """Callback when provider login fails."""
        self._cloud_states[provider.id] = ProviderState(
            status=ProviderStatus.ERROR,
            loading=False,
            error=error,
        )
        self._rebuild_list()
        if self._current_tab == self.TAB_CLOUD:
            self._rebuild_cloud_tree()
        if len(error) > 100:
            error = error[:100] + "..."
        self.notify(f"{provider.name} login failed: {error}", severity="error")

    def action_azure_logout(self) -> None:
        """Logout from a cloud provider (only when account is highlighted)."""
        # Check tree widget first for cloud tab
        if self._current_tab == self.TAB_CLOUD:
            tree_node = self._get_highlighted_tree_node()
            if tree_node and tree_node.data:
                data = tree_node.data
                if data.get("type") == "account":
                    provider_id = data.get("provider_id")
                    provider = next((p for p in self._cloud_providers if p.id == provider_id), None)
                    if provider:
                        self._start_provider_logout(provider)
            return

        # Fallback to option list
        option = self._get_highlighted_option()
        if option and option.id == "_azure_account":
            provider = next((p for p in self._cloud_providers if p.id == "azure"), None)
            if provider:
                self._start_provider_logout(provider)

    def action_azure_switch(self) -> None:
        """Switch cloud provider account (only when account is highlighted)."""
        # Check tree widget first for cloud tab
        if self._current_tab == self.TAB_CLOUD:
            tree_node = self._get_highlighted_tree_node()
            if tree_node and tree_node.data:
                data = tree_node.data
                if data.get("type") == "account":
                    provider_id = data.get("provider_id")
                    provider = next((p for p in self._cloud_providers if p.id == provider_id), None)
                    if provider:
                        self._start_provider_login(provider)
            return

        # Fallback to option list
        option = self._get_highlighted_option()
        if option and option.id == "_azure_account":
            provider = next((p for p in self._cloud_providers if p.id == "azure"), None)
            if provider:
                self._start_provider_login(provider)

    def _start_provider_logout(self, provider: CloudProvider) -> None:
        """Start logout process for a cloud provider."""
        self.notify(f"Logging out from {provider.name}...")
        self._cloud_states[provider.id] = ProviderState(loading=True)
        self._rebuild_list()
        self.run_worker(
            lambda: self._provider_logout_worker(provider),
            thread=True,
        )

    def _provider_logout_worker(self, provider: CloudProvider) -> None:
        """Worker to run provider logout."""
        success = provider.logout()
        self.app.call_from_thread(self._on_provider_logout_complete, provider, success)

    def _on_provider_logout_complete(self, provider: CloudProvider, success: bool) -> None:
        """Callback when provider logout completes."""
        from ...services.cloud import ProviderStatus

        if success:
            self._cloud_states[provider.id] = ProviderState(
                status=ProviderStatus.NOT_LOGGED_IN,
                loading=False,
            )
            self.notify(f"Logged out from {provider.name}")
        else:
            self._cloud_states[provider.id] = ProviderState(
                status=ProviderStatus.ERROR,
                loading=False,
                error="Logout failed",
            )
            self.notify(f"Failed to logout from {provider.name}", severity="warning")

        self._rebuild_list()
        if self._current_tab == self.TAB_CLOUD:
            self._rebuild_cloud_tree()

    def _load_provider_for_subscription(
        self, provider: CloudProvider, subscription_id: str, new_index: int
    ) -> None:
        """Load resources for a specific subscription."""
        # Update state to loading with new subscription index
        state = self._cloud_states.get(provider.id, ProviderState())
        state = ProviderState(
            loading=True,
            account=state.account,
            extra={
                **state.extra,
                "current_subscription_index": new_index,
            },
        )
        self._cloud_states[provider.id] = state
        self._rebuild_list()

        self.run_worker(
            lambda: self._discover_subscription_worker(provider, subscription_id, new_index),
            thread=True,
        )

    def _discover_subscription_worker(
        self, provider: CloudProvider, subscription_id: str, new_index: int
    ) -> None:
        """Worker to discover resources for a specific subscription."""
        from ...services.cloud_detector import (
            cache_subscriptions_and_servers,
            detect_azure_sql_resources,
        )

        try:
            status, servers = detect_azure_sql_resources(subscription_id, use_cache=True)

            # Get current state to preserve subscriptions
            current_state = self._cloud_states.get(provider.id, ProviderState())
            subscriptions = current_state.extra.get("subscriptions", [])

            # Cache servers
            if subscriptions:
                cache_subscriptions_and_servers(subscriptions, servers, subscription_id)

            self.app.call_from_thread(
                self._on_subscription_loaded, provider, servers, subscriptions, new_index
            )
        except Exception as e:
            self.app.call_from_thread(self._on_provider_error, provider.id, str(e))

    def _on_subscription_loaded(
        self,
        provider: CloudProvider,
        servers: list,
        subscriptions: list,
        new_index: int,
    ) -> None:
        """Callback when subscription resources are loaded."""
        from ...services.cloud import ProviderStatus

        current_state = self._cloud_states.get(provider.id, ProviderState())
        self._cloud_states[provider.id] = ProviderState(
            status=ProviderStatus.AVAILABLE,
            account=current_state.account,
            loading=False,
            extra={
                "subscriptions": subscriptions,
                "servers": servers,
                "current_subscription_index": new_index,
            },
        )

        self._rebuild_list()
        if self._current_tab == self.TAB_CLOUD:
            self._rebuild_cloud_tree()
        self._select_option_by_id(f"_azure_sub_{new_index}")
        self._update_shortcuts()

        # Auto-load databases
        self._auto_load_all_databases()

    def action_switch_tab(self) -> None:
        """Switch between Connections, Docker and Cloud tabs."""
        if self._current_tab == self.TAB_CONNECTIONS:
            self._current_tab = self.TAB_DOCKER
        elif self._current_tab == self.TAB_DOCKER:
            self._current_tab = self.TAB_CLOUD
        else:
            self._current_tab = self.TAB_CONNECTIONS

        self._update_dialog_title()
        self._update_widget_visibility()
        self._rebuild_list()
        self._update_shortcuts()

    def _update_widget_visibility(self) -> None:
        """Show/hide the appropriate widget based on current tab."""
        option_list = self.query_one("#picker-list", OptionList)
        cloud_tree = self.query_one("#cloud-tree", Tree)

        if self._current_tab == self.TAB_CLOUD:
            option_list.add_class("hidden")
            cloud_tree.add_class("visible")
            self._rebuild_cloud_tree()
        else:
            option_list.remove_class("hidden")
            cloud_tree.remove_class("visible")

    def _rebuild_cloud_tree(self) -> None:
        """Rebuild the cloud tree widget from provider states."""
        tree = self.query_one("#cloud-tree", Tree)
        tree.clear()
        tree.root.expand()

        for provider in self._cloud_providers:
            state = self._cloud_states.get(provider.id, ProviderState())
            self._add_provider_to_tree(tree.root, provider, state)

    def _add_provider_to_tree(
        self,
        parent: TreeNode,
        provider: "CloudProvider",
        state: ProviderState,
    ) -> None:
        """Add a cloud provider's resources to the tree."""
        # Provider header node
        provider_node = parent.add(f"[bold]{provider.name}[/]", expand=True)
        provider_node.data = {"type": "provider", "provider_id": provider.id}

        # Handle loading state
        if state.loading:
            provider_node.add_leaf("[dim italic]Loading...[/]")
            return

        # Handle different statuses
        if state.status == ProviderStatus.CLI_NOT_INSTALLED:
            provider_node.add_leaf(f"[dim]({provider.name.lower()} CLI not installed)[/]")
            return

        if state.status == ProviderStatus.NOT_LOGGED_IN:
            login_node = provider_node.add_leaf(f"🔑 Login to {provider.name}...")
            login_node.data = {"type": "login", "provider_id": provider.id}
            return

        if state.status == ProviderStatus.ERROR:
            provider_node.add_leaf(f"[red]⚠ {provider.name} error[/]")
            if state.error:
                provider_node.add_leaf(f"[dim]{state.error}[/]")
            return

        # Show account
        if state.account:
            account_display = state.account.username
            if len(account_display) > 40:
                account_display = account_display[:37] + "..."
            account_node = provider_node.add(f"👤 {account_display}", expand=True)
            account_node.data = {"type": "account", "provider_id": provider.id}

            # Provider-specific tree building
            if provider.id == "azure":
                self._add_azure_resources_to_tree(account_node, provider, state)
            elif provider.id == "aws":
                self._add_aws_resources_to_tree(account_node, provider, state)
            elif provider.id == "gcp":
                self._add_gcp_resources_to_tree(account_node, provider, state)

    def _add_azure_resources_to_tree(
        self,
        parent: TreeNode,
        provider: "CloudProvider",
        state: ProviderState,
    ) -> None:
        """Add Azure-specific resources to the tree."""
        subscriptions = state.extra.get("subscriptions", [])
        current_sub_index = state.extra.get("current_subscription_index", 0)
        servers = state.extra.get("servers", [])

        for i, sub in enumerate(subscriptions):
            sub_display = f"{sub.name[:40]}..." if len(sub.name) > 40 else sub.name
            is_active = i == current_sub_index

            if is_active:
                sub_node = parent.add(f"[green]🔑 ★ {sub_display}[/]", expand=True)
            else:
                sub_node = parent.add(f"[dim]🔑 {sub_display}[/]")
            sub_node.data = {"type": "subscription", "provider_id": "azure", "index": i}

            # Only show servers for active subscription
            if is_active and servers:
                for server in servers:
                    status_icon = "🟢" if server.state == "Ready" else "🟡"
                    auth_hint = ""
                    if server.entra_only_auth:
                        auth_hint = " [dim][Entra only][/]"
                    elif not server.has_entra_admin:
                        auth_hint = " [dim][SQL only][/]"

                    server_node = sub_node.add(
                        f"{status_icon} {server.name}{auth_hint}",
                        expand=True
                    )
                    server_node.data = {"type": "server", "provider_id": "azure", "server": server}

                    if server.databases:
                        for db in server.databases:
                            # Add Entra option if available
                            if server.has_entra_admin:
                                saved = self._is_azure_connection_saved(server, db, False)
                                if saved:
                                    db_node = server_node.add_leaf(f"[dim]{db} Entra ✓[/]")
                                else:
                                    db_node = server_node.add_leaf(f"{db} [dim]Entra[/]")
                                db_node.data = {
                                    "type": "database",
                                    "provider_id": "azure",
                                    "server": server,
                                    "database": db,
                                    "auth_type": "ad",
                                }

                            # Add SQL Auth option if available
                            if not server.entra_only_auth:
                                saved = self._is_azure_connection_saved(server, db, True)
                                if saved:
                                    db_node = server_node.add_leaf(f"[dim]{db} SQL Auth ✓[/]")
                                else:
                                    db_node = server_node.add_leaf(f"{db} [dim]SQL Auth[/]")
                                db_node.data = {
                                    "type": "database",
                                    "provider_id": "azure",
                                    "server": server,
                                    "database": db,
                                    "auth_type": "sql",
                                }
                    else:
                        server_node.add_leaf("[dim](no databases)[/]")
            elif is_active:
                sub_node.add_leaf("[dim](no SQL servers)[/]")

    def _add_aws_resources_to_tree(
        self,
        parent: TreeNode,
        provider: "CloudProvider",
        state: ProviderState,
    ) -> None:
        """Add AWS-specific resources to the tree."""
        regions_with_resources = state.extra.get("regions_with_resources", [])

        if not regions_with_resources:
            parent.add_leaf("[dim](no databases found)[/]")
            return

        for region_resources in regions_with_resources:
            region = region_resources.region
            region_node = parent.add(f"[green]📍 {region}[/]", expand=True)
            region_node.data = {"type": "region", "provider_id": "aws", "region": region}

            # RDS Instances
            for instance in region_resources.rds_instances:
                engine_display = instance.engine.replace("-", " ").title()
                status_icon = "🟢" if instance.status == "available" else "🟡"
                saved = self._is_aws_rds_saved(instance)

                if saved:
                    inst_node = region_node.add_leaf(
                        f"[dim]{status_icon} {instance.identifier} [{engine_display}] ✓[/]"
                    )
                else:
                    inst_node = region_node.add_leaf(
                        f"{status_icon} {instance.identifier} [dim][{engine_display}][/]"
                    )
                inst_node.data = {
                    "type": "rds_instance",
                    "provider_id": "aws",
                    "instance": instance,
                    "region": region,
                }

            # Redshift Clusters
            for cluster in region_resources.redshift_clusters:
                status_icon = "🟢" if cluster.status == "available" else "🟡"
                saved = self._is_aws_redshift_saved(cluster)

                if saved:
                    cluster_node = region_node.add_leaf(
                        f"[dim]{status_icon} {cluster.identifier} [Redshift] ✓[/]"
                    )
                else:
                    cluster_node = region_node.add_leaf(
                        f"{status_icon} {cluster.identifier} [dim][Redshift][/]"
                    )
                cluster_node.data = {
                    "type": "redshift_cluster",
                    "provider_id": "aws",
                    "cluster": cluster,
                    "region": region,
                }

    def _add_gcp_resources_to_tree(
        self,
        parent: TreeNode,
        provider: "CloudProvider",
        state: ProviderState,
    ) -> None:
        """Add GCP-specific resources to the tree."""
        project = state.extra.get("project", "")
        instances = state.extra.get("instances", [])

        if project:
            project_node = parent.add(f"[dim]Project: {project}[/]", expand=True)
            project_node.data = {"type": "project", "provider_id": "gcp", "project": project}

            if instances:
                for instance in instances:
                    engine_display = instance.database_version.replace("_", " ")
                    status_icon = "🟢" if instance.state == "RUNNABLE" else "🟡"
                    saved = self._is_gcp_instance_saved(instance)

                    if saved:
                        inst_node = project_node.add_leaf(
                            f"[dim]{status_icon} {instance.name} [{engine_display}] ✓[/]"
                        )
                    else:
                        inst_node = project_node.add_leaf(
                            f"{status_icon} {instance.name} [dim][{engine_display}][/]"
                        )
                    inst_node.data = {
                        "type": "cloud_sql_instance",
                        "provider_id": "gcp",
                        "instance": instance,
                    }
            else:
                project_node.add_leaf("[dim](no Cloud SQL instances)[/]")

    def _is_azure_connection_saved(self, server: "AzureSqlServer", database: str, use_sql_auth: bool) -> bool:
        """Check if an Azure connection is already saved."""
        for conn in self.connections:
            if conn.source != "azure":
                continue
            if conn.server == server.fqdn and conn.database == database:
                conn_is_sql = conn.options.get("auth_type") == "sql"
                if conn_is_sql == use_sql_auth:
                    return True
        return False

    def _is_aws_rds_saved(self, instance) -> bool:
        """Check if an RDS instance is already saved."""
        for conn in self.connections:
            if conn.source != "aws":
                continue
            if conn.server == instance.endpoint:
                return True
        return False

    def _is_aws_redshift_saved(self, cluster) -> bool:
        """Check if a Redshift cluster is already saved."""
        for conn in self.connections:
            if conn.source != "aws":
                continue
            if conn.server == cluster.endpoint:
                return True
        return False

    def _is_gcp_instance_saved(self, instance) -> bool:
        """Check if a GCP instance is already saved."""
        for conn in self.connections:
            if conn.source != "gcp":
                continue
            if conn.options.get("gcp_connection_name") == instance.connection_name:
                return True
            if instance.ip_address and conn.server == instance.ip_address:
                return True
        return False

    def action_save_docker(self) -> None:
        """Save the selected Docker container or cloud resource as a connection."""
        # Handle tree-based saves for cloud tab
        if self._current_tab == self.TAB_CLOUD:
            self._save_cloud_tree_node()
            return

        option = self._get_highlighted_option()
        if not option or option.disabled:
            return

        option_id = str(option.id) if option.id else ""

        # Check if a cloud provider handles this option
        for provider in self._cloud_providers:
            if provider.is_my_option(option_id):
                state = self._cloud_states.get(provider.id, ProviderState())
                result = provider.handle_action("save", option_id, state, self.connections)

                if result.action == "save" and result.config:
                    self._save_cloud_connection(result.config, option_id)
                elif result.action == "none":
                    self.notify("Connection already saved", severity="warning")
                return

        # Docker container
        if self._is_docker_option(option):
            container_id = str(option.id)[len(self.DOCKER_PREFIX):]
            container = self._get_container_by_id(container_id)
            if container:
                if self._is_container_saved(container):
                    self.notify("Container already saved", severity="warning")
                    return
                self._save_container(container)

    def _save_cloud_tree_node(self) -> None:
        """Save a cloud resource from the tree widget."""
        tree_node = self._get_highlighted_tree_node()
        if not tree_node or not tree_node.data:
            return

        data = tree_node.data
        node_type = data.get("type")
        provider_id = data.get("provider_id")

        config = None

        # Azure database
        if node_type == "database" and provider_id == "azure":
            server = data.get("server")
            database = data.get("database")
            auth_type = data.get("auth_type", "ad")
            if server and database:
                if self._is_azure_connection_saved(server, database, auth_type == "sql"):
                    self.notify("Connection already saved", severity="warning")
                    return
                # Build config from Azure provider
                from ...config import ConnectionConfig
                config = ConnectionConfig(
                    name=f"{server.name}/{database}",
                    db_type="mssql",
                    server=server.fqdn,
                    port="1433",
                    database=database,
                    username=server.admin_login or "",
                    password=None,
                    source="azure",
                    options={
                        "auth_type": auth_type,
                        "azure_subscription_id": server.subscription_id,
                        "azure_resource_group": server.resource_group,
                    },
                )

        # AWS RDS instance
        elif node_type == "rds_instance" and provider_id == "aws":
            instance = data.get("instance")
            if instance:
                if self._is_aws_rds_saved(instance):
                    self.notify("Connection already saved", severity="warning")
                    return
                provider = next((p for p in self._cloud_providers if p.id == "aws"), None)
                if provider:
                    state = self._cloud_states.get("aws", ProviderState())
                    result = provider.handle_action(
                        "save",
                        f"aws:rds:{instance.identifier}",
                        state,
                        self.connections
                    )
                    config = result.config

        # AWS Redshift cluster
        elif node_type == "redshift_cluster" and provider_id == "aws":
            cluster = data.get("cluster")
            if cluster:
                if self._is_aws_redshift_saved(cluster):
                    self.notify("Connection already saved", severity="warning")
                    return
                provider = next((p for p in self._cloud_providers if p.id == "aws"), None)
                if provider:
                    state = self._cloud_states.get("aws", ProviderState())
                    result = provider.handle_action(
                        "save",
                        f"aws:redshift:{cluster.identifier}",
                        state,
                        self.connections
                    )
                    config = result.config

        # GCP Cloud SQL instance
        elif node_type == "cloud_sql_instance" and provider_id == "gcp":
            instance = data.get("instance")
            if instance:
                if self._is_gcp_instance_saved(instance):
                    self.notify("Connection already saved", severity="warning")
                    return
                provider = next((p for p in self._cloud_providers if p.id == "gcp"), None)
                if provider:
                    state = self._cloud_states.get("gcp", ProviderState())
                    result = provider.handle_action(
                        "save",
                        f"gcp:sql:{instance.name}",
                        state,
                        self.connections
                    )
                    config = result.config

        if config:
            self._save_cloud_connection_from_tree(config)

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

    def _save_cloud_connection(self, config: ConnectionConfig, option_id: str) -> None:
        """Save a cloud connection without closing the modal."""
        from ...config import save_connections

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

        # Refresh the list to update saved indicators
        self._rebuild_list()

        # Refresh the app's explorer tree to show new connection
        if hasattr(self.app, "refresh_tree"):
            self.app.refresh_tree()

        # Restore cursor position
        self._select_option_by_id(option_id)

    def _save_cloud_connection_from_tree(self, config: ConnectionConfig) -> None:
        """Save a cloud connection from tree widget without closing the modal."""
        from ...config import save_connections

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

        # Rebuild tree to update saved indicators
        self._rebuild_cloud_tree()

        # Refresh the app's explorer tree to show new connection
        if hasattr(self.app, "refresh_tree"):
            self.app.refresh_tree()

        self._update_shortcuts()

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
        """Refresh Docker containers and cloud resources (clears cache)."""
        from ...services.cloud.aws.cache import clear_aws_cache
        from ...services.cloud.gcp.cache import clear_gcp_cache
        from ...services.cloud_detector import clear_azure_cache

        # Clear all cloud caches to force fresh data
        clear_azure_cache()
        clear_aws_cache()
        clear_gcp_cache()

        self._load_containers_async()
        self._load_cloud_providers_async()
        self.notify("Refreshing...")

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle tree node selection in cloud tab."""
        if event.control.id != "cloud-tree":
            return

        node = event.node
        data = node.data
        if not data:
            return

        node_type = data.get("type")
        provider_id = data.get("provider_id")

        # Handle login nodes
        if node_type == "login":
            provider = next((p for p in self._cloud_providers if p.id == provider_id), None)
            if provider:
                self._start_provider_login(provider)
            return

        # Handle subscription switching for Azure
        if node_type == "subscription" and provider_id == "azure":
            sub_index = data.get("index", 0)
            provider = next((p for p in self._cloud_providers if p.id == "azure"), None)
            if provider:
                self._activate_subscription(provider, sub_index)
            return

        # Handle Azure database selection
        if node_type == "database" and provider_id == "azure":
            server = data.get("server")
            database = data.get("database")
            auth_type = data.get("auth_type", "ad")
            if server and database:
                self.dismiss(AzureConnectionResult(
                    server=server,
                    database=database,
                    use_sql_auth=(auth_type == "sql"),
                ))
            return

        # Handle AWS RDS instance selection
        if node_type == "rds_instance" and provider_id == "aws":
            instance = data.get("instance")
            if instance:
                provider = next((p for p in self._cloud_providers if p.id == "aws"), None)
                if provider:
                    state = self._cloud_states.get("aws", ProviderState())
                    result = provider.handle_action(
                        "select",
                        f"aws:rds:{instance.identifier}",
                        state,
                        self.connections
                    )
                    if result.config:
                        self.dismiss(CloudConnectionResult(
                            config=result.config,
                            provider_id="aws",
                        ))
            return

        # Handle AWS Redshift cluster selection
        if node_type == "redshift_cluster" and provider_id == "aws":
            cluster = data.get("cluster")
            if cluster:
                provider = next((p for p in self._cloud_providers if p.id == "aws"), None)
                if provider:
                    state = self._cloud_states.get("aws", ProviderState())
                    result = provider.handle_action(
                        "select",
                        f"aws:redshift:{cluster.identifier}",
                        state,
                        self.connections
                    )
                    if result.config:
                        self.dismiss(CloudConnectionResult(
                            config=result.config,
                            provider_id="aws",
                        ))
            return

        # Handle GCP Cloud SQL instance selection
        if node_type == "cloud_sql_instance" and provider_id == "gcp":
            instance = data.get("instance")
            if instance:
                provider = next((p for p in self._cloud_providers if p.id == "gcp"), None)
                if provider:
                    state = self._cloud_states.get("gcp", ProviderState())
                    result = provider.handle_action(
                        "select",
                        f"gcp:sql:{instance.name}",
                        state,
                        self.connections
                    )
                    if result.config:
                        self.dismiss(CloudConnectionResult(
                            config=result.config,
                            provider_id="gcp",
                        ))
            return

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        """Update shortcuts when tree selection changes."""
        if event.control.id == "cloud-tree":
            self._update_shortcuts()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle option selection via click."""
        if event.option_list.id == "picker-list":
            option = event.option
            if option and not option.disabled:
                option_id = str(option.id) if option.id else ""

                # Check if a cloud provider handles this option
                for provider in self._cloud_providers:
                    if provider.is_my_option(option_id):
                        state = self._cloud_states.get(provider.id, ProviderState())
                        result = provider.handle_action("select", option_id, state, self.connections)

                        if result.action == "login":
                            self._start_provider_login(provider)
                        elif result.action == "switch_subscription":
                            sub_index = result.metadata.get("subscription_index", 0)
                            self._activate_subscription(provider, sub_index)
                        elif result.action == "connect" and result.config:
                            # Use Azure-specific result for Azure provider
                            if provider.id == "azure":
                                self.dismiss(AzureConnectionResult(
                                    server=self._get_server_from_config(result.config, state),
                                    database=result.config.database,
                                    use_sql_auth=result.config.options.get("auth_type") == "sql",
                                ))
                            else:
                                # Generic cloud result for AWS, GCP, etc.
                                self.dismiss(CloudConnectionResult(
                                    config=result.config,
                                    provider_id=provider.id,
                                ))
                        # For "none" action or account clicks, do nothing
                        return

                # Docker container
                if self._is_docker_option(option):
                    container_id = str(option.id)[len(self.DOCKER_PREFIX):]
                    container = self._get_container_by_id(container_id)
                    if container:
                        self.dismiss(DockerConnectionResult(container=container, action="connect"))
                    return

                # Saved connection
                self.dismiss(option.id)
