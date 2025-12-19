"""Connection picker screen with fuzzy search and Docker container detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from ...utils import fuzzy_match, highlight_matches
from ...widgets import Dialog, FilterInput

if TYPE_CHECKING:
    from ...config import ConnectionConfig
    from ...services.docker_detector import DetectedContainer


@dataclass
class DockerConnectionResult:
    """Result when selecting a Docker container."""

    container: DetectedContainer
    action: str  # "connect" or "save"


class ConnectionPickerScreen(ModalScreen):
    """Modal screen for selecting a connection with fuzzy search."""

    BINDINGS = [
        Binding("escape", "cancel_or_close_filter", "Cancel"),
        Binding("enter", "select", "Select"),
        Binding("s", "save_docker", "Save", show=True),
        Binding("n", "new_connection", "New", show=True),
        Binding("f", "refresh", "Refresh", show=False),
        Binding("slash", "open_filter", "Search", show=True),
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("backspace", "backspace", "Backspace", show=False),
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
        height: auto;
        max-height: 20;
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

    def __init__(self, connections: list[ConnectionConfig]):
        super().__init__()
        self.connections = connections
        self.search_text = ""
        self._filter_active = False
        self._docker_containers: list[DetectedContainer] = []
        self._docker_status_message: str | None = None

    def compose(self) -> ComposeResult:
        with Dialog(id="picker-dialog", title="Connect"):
            yield FilterInput(id="picker-filter")
            yield OptionList(id="picker-list")

    def on_mount(self) -> None:
        """Load Docker containers when screen mounts."""
        self._detect_docker_containers()
        self._rebuild_list()
        self._update_shortcuts()

    def _update_shortcuts(self) -> None:
        """Update dialog shortcuts based on current selection."""
        option = self._get_highlighted_option()
        show_save = False

        if option and self._is_docker_option(option):
            container_id = str(option.id)[len(self.DOCKER_PREFIX):]
            container = self._get_container_by_id(container_id)
            if container and not self._is_container_saved(container):
                show_save = True

        shortcuts = [("Select", "enter")]
        if show_save:
            shortcuts.append(("Save", "s"))
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

    def _detect_docker_containers(self) -> None:
        """Detect Docker database containers."""
        from ...services.docker_detector import DockerStatus, detect_database_containers

        status, containers = detect_database_containers()

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
            # We have containers - status message not needed
            self._docker_status_message = None

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
        """Build option list with fuzzy highlighting and sections."""
        options: list[Option] = []

        # Filter saved connections
        saved_options = []
        for conn in self.connections:
            matches, indices = fuzzy_match(pattern, conn.name)
            if matches or not pattern:
                display = highlight_matches(conn.name, indices)
                db_type = conn.db_type.upper() if conn.db_type else "DB"
                info = conn.get_display_info()
                saved_options.append(
                    Option(f"{display} [{db_type}] [dim]({info})[/]", id=conn.name)
                )

        # Filter Docker containers - separate running and exited
        running_options = []
        exited_options = []
        for container in self._docker_containers:
            matches, indices = fuzzy_match(pattern, container.container_name)
            if matches or not pattern:
                display = highlight_matches(container.container_name, indices)
                db_label = container.get_display_name().split("(")[-1].rstrip(")")
                port_info = f":{container.port}" if container.port else ""

                is_saved = self._is_container_saved(container)
                if container.is_running:
                    saved_indicator = "✓ saved" if is_saved else "[dim]not saved[/]"
                    running_options.append(
                        Option(
                            f"🐳 {display} [{db_label}] [dim](localhost{port_info})[/] {saved_indicator}",
                            id=f"{self.DOCKER_PREFIX}{container.container_id}",
                        )
                    )
                else:
                    # Exited containers - muted gold styling, selectable but not connectable
                    saved_indicator = "[#CEBB91]✓ saved[/]" if is_saved else ""
                    suffix = f" {saved_indicator}" if saved_indicator else ""
                    exited_options.append(
                        Option(
                            f"[#CEBB91]🐳 {display} [{db_label}] (Exited)[/]{suffix}",
                            id=f"{self.DOCKER_PREFIX}{container.container_id}",
                        )
                    )

        # Add Saved section
        options.append(Option("[bold]Saved[/]", id="_header_saved", disabled=True))

        if saved_options:
            options.extend(saved_options)
        else:
            options.append(
                Option("[dim](no saved connections)[/]", id="_empty_saved", disabled=True)
            )

        # Add Docker section (running containers)
        options.append(Option("", id="_spacer", disabled=True))
        options.append(Option("[bold]Docker[/]", id="_header_docker", disabled=True))

        if running_options:
            options.extend(running_options)
        elif self._docker_status_message:
            options.append(
                Option(f"[dim]{self._docker_status_message}[/]", id="_docker_status", disabled=True)
            )
        else:
            options.append(
                Option("[dim](no running containers)[/]", id="_docker_empty", disabled=True)
            )

        # Add Docker unavailable section (exited containers)
        if exited_options:
            options.append(Option("", id="_spacer2", disabled=True))
            options.append(Option("[bold]Docker unavailable[/]", id="_header_docker_unavailable", disabled=True))
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

        if self._is_docker_option(option):
            # Docker container - connect directly
            container_id = str(option.id)[len(self.DOCKER_PREFIX) :]
            container = self._get_container_by_id(container_id)
            if container:
                if not container.is_running:
                    self.notify("Container is not running", severity="warning")
                    return
                self.dismiss(DockerConnectionResult(container=container, action="connect"))
        else:
            # Saved connection
            self.dismiss(option.id)

    def action_save_docker(self) -> None:
        """Save the selected Docker container as a connection (stays in modal)."""
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

        # Restore cursor to the same container
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
        """Refresh Docker containers list."""
        self._detect_docker_containers()
        self._rebuild_list()
        self._update_shortcuts()
        self.notify("Refreshed")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle option selection via click."""
        if event.option_list.id == "picker-list":
            option = event.option
            if option and not option.disabled:
                if self._is_docker_option(option):
                    container_id = str(option.id)[len(self.DOCKER_PREFIX) :]
                    container = self._get_container_by_id(container_id)
                    if container:
                        self.dismiss(DockerConnectionResult(container=container, action="connect"))
                else:
                    self.dismiss(option.id)
