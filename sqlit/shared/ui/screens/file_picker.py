"""File picker dialog screen with directory browser."""

from __future__ import annotations

from enum import Enum, auto
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Input, ListItem, ListView, Static

from sqlit.shared.ui.widgets import Dialog


class FilePickerMode(Enum):
    """Mode for the file picker dialog."""

    SAVE = auto()  # Save a new file (filename can be new)
    OPEN = auto()  # Open an existing file (must select existing file)


class FilePickerScreen(ModalScreen[str | None]):
    """Modal screen for file selection with directory browser.

    Returns the full file path on submit, or None on cancel.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("tab", "toggle_focus", "Switch focus", show=False),
        Binding("shift+tab", "toggle_focus", "Switch focus", show=False),
        Binding("s", "save", "Save", show=False),
    ]

    CSS = """
    FilePickerScreen {
        align: center middle;
        background: transparent;
    }

    #file-picker-dialog {
        width: 70;
        height: 22;
    }

    #file-browser {
        height: 12;
        border: solid $panel;
        background: $surface;
        margin-bottom: 1;
    }

    #file-browser:focus-within {
        border: solid $primary;
    }

    #file-browser ListView {
        height: 100%;
        background: $surface;
    }

    #file-browser ListItem {
        padding: 0 1;
    }

    #path-container {
        border: solid $panel;
        background: $surface;
        padding: 0;
        height: 3;
        border-title-align: left;
        border-title-color: $text-muted;
        border-title-background: $surface;
        border-title-style: none;
    }

    #path-container:focus-within {
        border: solid $primary;
        border-title-color: $primary;
    }

    #path-container Input {
        border: none;
        height: 1;
        padding: 0;
        background: $surface;
    }

    #path-container Input:focus {
        border: none;
        background-tint: $foreground 5%;
    }
    """

    def __init__(
        self,
        mode: FilePickerMode = FilePickerMode.SAVE,
        title: str | None = None,
        default_filename: str = "",
        start_directory: str | Path | None = None,
        start_path: str | Path | None = None,
        file_extensions: list[str] | None = None,
    ):
        """Initialize file picker.

        Args:
            mode: SAVE for saving files, OPEN for selecting existing files.
            title: Dialog title. Defaults to "Save File" or "Open File" based on mode.
            default_filename: Default filename for SAVE mode.
            start_directory: Initial directory to show.
            start_path: Initial file path (overrides start_directory if set).
            file_extensions: List of extensions to filter (e.g., [".db", ".sqlite"]).
                            Only files with these extensions will be shown.
        """
        super().__init__()
        self.mode = mode
        self.title_text = title or ("Save File" if mode == FilePickerMode.SAVE else "Open File")
        self.default_filename = default_filename
        self.file_extensions = [ext.lower() for ext in (file_extensions or [])]
        self._updating_input = False

        # Determine initial directory and filename
        if start_path:
            path = Path(start_path).expanduser()
            if path.is_file():
                self._current_dir = path.parent.resolve()
                self._initial_filename = path.name
            elif path.is_dir():
                self._current_dir = path.resolve()
                self._initial_filename = default_filename
            else:
                # Path doesn't exist - use parent if it exists
                if path.parent.is_dir():
                    self._current_dir = path.parent.resolve()
                    self._initial_filename = path.name
                else:
                    self._current_dir = Path(start_directory or Path.cwd()).resolve()
                    self._initial_filename = default_filename
        else:
            self._current_dir = Path(start_directory or Path.cwd()).resolve()
            self._initial_filename = default_filename

    def compose(self) -> ComposeResult:
        if self.mode == FilePickerMode.SAVE:
            shortcuts: list[tuple[str, str]] = [("Save", "s")]
        else:
            shortcuts = [("Select", "enter")]
        with Dialog(id="file-picker-dialog", title=self.title_text, shortcuts=shortcuts):
            with Container(id="file-browser"):
                yield ListView(id="file-list")
            container = Container(id="path-container")
            container.border_title = "Path"
            with container:
                initial_value = str(self._current_dir / self._initial_filename) if self._initial_filename else str(self._current_dir)
                yield Input(
                    value=initial_value,
                    placeholder="/path/to/file",
                    id="path-input",
                )

    async def on_mount(self) -> None:
        await self._refresh_file_list()
        self.query_one("#file-list", ListView).focus()

    def _matches_extension(self, path: Path) -> bool:
        """Check if file matches the extension filter."""
        if not self.file_extensions:
            return True
        return path.suffix.lower() in self.file_extensions

    async def _refresh_file_list(self, update_input: bool = True) -> None:
        """Refresh the file list for current directory."""
        list_view = self.query_one("#file-list", ListView)
        had_focus = list_view.has_focus
        await list_view.clear()
        self._entries: list[Path | None] = []
        items: list[ListItem] = []

        # Add parent directory entry
        if self._current_dir.parent != self._current_dir:
            item = ListItem(Static("📁 .."))
            items.append(item)
            self._entries.append(None)  # None = parent

        # Get directory contents
        try:
            entries = sorted(self._current_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            items.append(ListItem(Static("⚠️  Permission denied")))
            await list_view.extend(items)
            return

        for entry in entries:
            if entry.name.startswith("."):
                continue  # Skip hidden files
            if entry.is_dir():
                item = ListItem(Static(f"📁 {entry.name}"))
                items.append(item)
                self._entries.append(entry)
            elif self._matches_extension(entry):
                item = ListItem(Static(f"📄 {entry.name}"))
                items.append(item)
                self._entries.append(entry)

        if items:
            await list_view.extend(items)

        # Select the first item (usually "..") so user can keep pressing enter to go up
        if self._entries:
            list_view.index = 0
        if had_focus:
            list_view.focus()

    def _update_path_input(self, filename: str | None = None) -> None:
        """Update the path input to reflect current directory and filename."""
        if self._updating_input:
            return
        self._updating_input = True
        try:
            path_input = self.query_one("#path-input", Input)
            current_path = Path(path_input.value)
            # Keep existing filename if not specified
            if filename is None:
                if current_path.is_dir() or not current_path.name:
                    filename = self.default_filename
                else:
                    filename = current_path.name
            if filename:
                path_input.value = str(self._current_dir / filename)
            else:
                path_input.value = str(self._current_dir)
        finally:
            self._updating_input = False

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle selection in file list."""
        list_view = self.query_one("#file-list", ListView)
        index = list_view.index
        if index is None or index >= len(self._entries):
            return

        entry = self._entries[index]

        if entry is None:
            # Go to parent directory
            self._current_dir = self._current_dir.parent
            await self._refresh_file_list()
            self._update_path_input()
            return

        if entry.is_dir():
            # Navigate into directory
            self._current_dir = entry
            await self._refresh_file_list()
            self._update_path_input()
        else:
            # File selected
            if self.mode == FilePickerMode.OPEN:
                # In open mode, selecting a file immediately completes the dialog
                self.dismiss(str(entry))
            else:
                # In save mode, put the filename in input for potential modification
                self._update_path_input(entry.name)
                self.query_one("#path-input", Input).focus()

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle path input changes - sync explorer with typed path."""
        if event.input.id != "path-input" or self._updating_input:
            return

        path = Path(event.value).expanduser()

        # If it's a directory, navigate to it
        if path.is_dir():
            if path != self._current_dir:
                self._current_dir = path.resolve()
                await self._refresh_file_list(update_input=False)
        # If parent directory exists, navigate to it
        elif path.parent.is_dir():
            if path.parent.resolve() != self._current_dir:
                self._current_dir = path.parent.resolve()
                await self._refresh_file_list(update_input=False)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "path-input":
            await self._submit_path(event.value)

    async def _submit_path(self, path_str: str) -> None:
        path_str = path_str.strip()
        if not path_str:
            self.notify("Path cannot be empty", severity="warning")
            return

        path = Path(path_str).expanduser()

        # If it's a directory, navigate into it
        if path.is_dir():
            self._current_dir = path.resolve()
            await self._refresh_file_list()
            if self.mode == FilePickerMode.SAVE and self.default_filename:
                self._update_path_input(self.default_filename)
            return

        # Validate for open mode
        if self.mode == FilePickerMode.OPEN:
            if not path.exists():
                self.notify("File does not exist", severity="warning")
                return
            if self.file_extensions and not self._matches_extension(path):
                exts = ", ".join(self.file_extensions)
                self.notify(f"File must have extension: {exts}", severity="warning")
                return

        # Return the path
        self.dismiss(str(path))

    def action_toggle_focus(self) -> None:
        """Toggle focus between file list and path input."""
        file_list = self.query_one("#file-list", ListView)
        path_input = self.query_one("#path-input", Input)

        if file_list.has_focus:
            path_input.focus()
        else:
            file_list.focus()

    async def action_save(self) -> None:
        if self.mode != FilePickerMode.SAVE:
            return
        path_input = self.query_one("#path-input", Input)
        await self._submit_path(path_input.value)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if self.app.screen is not self:
            return False
        if action == "save" and self.mode != FilePickerMode.SAVE:
            return False
        return super().check_action(action, parameters)
