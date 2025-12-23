"""Vim mode plugin for sqlit.

This plugin provides vim-like keybindings for the query editor.
All vim functionality is contained here - the main app only needs
to load plugins and route keys through them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.binding import Binding
from textual.events import Key
from textual.widgets import Tree

from .. import LeaderCommand, Plugin

if TYPE_CHECKING:
    from ...app import SSMSTUI

from .engine import VimEngine, VimMode, CommandAction


class VimModePlugin(Plugin):
    """Plugin providing vim mode for the query editor.

    Features:
    - Normal/Insert/Visual/Command modes
    - Vim motions (h/j/k/l, w/b/e, etc.)
    - Operators (d, c, y)
    - Text objects (iw, aw, i", etc.)
    - Command mode (:w, :q, :wq)
    - Toggle with <space>v
    """

    name = "vim_mode"

    def __init__(self) -> None:
        self.enabled: bool = False
        self.engine: VimEngine | None = None
        self._app: "SSMSTUI | None" = None

    def register(self, app: "SSMSTUI") -> None:
        """Initialize the vim engine and set up hooks."""
        self._app = app

        # Initialize vim engine for the query input
        self.engine = VimEngine(app.query_input)
        self.engine.set_mode_callback(self._on_mode_change)
        self.engine.set_command_callback(self._on_command_start)
        self.engine.set_command_update_callback(self._on_command_update)

        # Patch the Tree widget to redirect space to leader key
        self._patch_tree_widget(app)

    def _patch_tree_widget(self, app: "SSMSTUI") -> None:
        """Patch Tree's toggle_node action to call leader_key instead.

        This allows space to work as leader key even when Tree has focus.
        """
        tree = app.object_tree

        # Store original action
        original_toggle = tree.action_toggle_node

        def patched_toggle_node() -> None:
            # Call app's leader key action instead of toggling node
            app.action_leader_key()

        # Replace the action
        tree.action_toggle_node = patched_toggle_node

    def on_key(self, app: "SSMSTUI", event: Any) -> bool:
        """Handle key events when vim mode is enabled.

        Returns True if the key was consumed.
        """
        if not self.enabled:
            return False

        if not isinstance(event, Key):
            return False

        # Don't intercept keys when a modal screen is open
        from textual.screen import ModalScreen
        if len(app.screen_stack) > 1 and isinstance(app.screen_stack[-1], ModalScreen):
            return False

        # Only handle keys when query input has focus
        if not app.query_input.has_focus:
            return False

        # Let space trigger leader key in normal mode
        if event.key == "space" and app.editor_mode == VimMode.NORMAL:
            app.action_leader_key()
            return True

        # In NORMAL mode, let navigation keys pass through to app bindings
        # This allows e/q/r to switch panes instead of being vim motions
        if app.editor_mode == VimMode.NORMAL and event.key in ("e", "q", "r"):
            return False

        # Route to vim engine
        return self._handle_vim_key(app, event)

    def _handle_vim_key(self, app: "SSMSTUI", event: Key) -> bool:
        """Handle a key event through the vim engine."""
        if self.engine is None:
            return False

        # Convert Textual key to vim key format
        key = self._convert_key(event)

        # Handle the key through vim engine
        result = self.engine.handle_key(key)

        if not result.consumed:
            return False

        # Handle command actions
        if result.command_action:
            self._handle_command_action(app, result.command_action, result.message)

        # Handle insert mode entry
        if result.enter_insert:
            app.query_input.read_only = False

        # Show message if any
        if result.message and not result.command_action:
            app.notify(result.message)

        return True

    def _convert_key(self, event: Key) -> str:
        """Convert a Textual Key event to vim key format."""
        key = event.key

        # Handle special keys
        if key == "ctrl+left_square_bracket":
            return "ctrl+["
        if key == "escape":
            return "escape"
        if key in ("enter", "return"):
            return "enter"
        if key in ("backspace", "ctrl+h"):
            return "backspace"
        if key == "tab":
            return "tab"

        # Handle character keys
        if event.character and len(event.character) == 1:
            return event.character

        return key

    def _on_mode_change(self, mode: VimMode) -> None:
        """Handle vim mode changes."""
        if self._app is None:
            return

        from ...widgets import VimCommandLine

        app = self._app

        if mode == VimMode.INSERT:
            app.editor_mode = VimMode.INSERT
            app.query_input.read_only = False
        elif mode == VimMode.COMMAND:
            # Keep in NORMAL for status bar, but show command line
            app.editor_mode = VimMode.NORMAL
            try:
                cmd_line = app.query_one("#vim-command-line", VimCommandLine)
                cmd_line.show()
            except Exception:
                pass
        else:
            # NORMAL, VISUAL, OPERATOR_PENDING, etc. all show as NORMAL
            app.editor_mode = VimMode.NORMAL
            app.query_input.read_only = True
            # Hide command line if visible
            try:
                cmd_line = app.query_one("#vim-command-line", VimCommandLine)
                cmd_line.hide()
            except Exception:
                pass

        app._update_status_bar()
        app._update_footer_bindings()

    def _on_command_start(self, text: str) -> None:
        """Handle entering command mode."""
        if self._app is None:
            return

        from ...widgets import VimCommandLine

        try:
            cmd_line = self._app.query_one("#vim-command-line", VimCommandLine)
            cmd_line.set_command(text)
            cmd_line.show()
        except Exception:
            pass

    def _on_command_update(self, text: str) -> None:
        """Handle command line updates."""
        if self._app is None:
            return

        from ...widgets import VimCommandLine

        try:
            cmd_line = self._app.query_one("#vim-command-line", VimCommandLine)
            cmd_line.set_command(text)
        except Exception:
            pass

    def _handle_command_action(
        self, app: "SSMSTUI", action: CommandAction, message: str
    ) -> None:
        """Handle a command action from command mode."""
        from ...widgets import VimCommandLine

        # Hide command line
        try:
            cmd_line = app.query_one("#vim-command-line", VimCommandLine)
            cmd_line.hide()
        except Exception:
            pass

        if action == CommandAction.QUIT:
            # Just exit to normal mode, stay in query editor
            pass

        elif action == CommandAction.QUIT_FORCE:
            # Force exit - discard query and leave editor
            self._exit_query_editing(app, discard=True)

        elif action == CommandAction.WRITE:
            # Save query to history
            self._save_query_to_history(app)
            if message:
                app.notify(message)

        elif action == CommandAction.WRITE_QUIT:
            # Save and exit
            self._save_query_to_history(app)
            self._exit_query_editing(app)

        elif action == CommandAction.NONE:
            # Just exiting command mode, show message if any
            if message:
                severity = "error" if "Unknown" in message else "information"
                app.notify(message, severity=severity)

    def _exit_query_editing(self, app: "SSMSTUI", discard: bool = False) -> None:
        """Exit query editing mode."""
        app.editor_mode = VimMode.NORMAL
        app.query_input.read_only = True

        if self.engine:
            self.engine.exit_insert_mode()

        if discard:
            app.query_input.text = ""

        app.results_table.focus()
        app._update_status_bar()
        app._update_footer_bindings()

    def _save_query_to_history(self, app: "SSMSTUI") -> None:
        """Save the current query to history."""
        if not app.current_config:
            return

        query = app.query_input.text.strip()
        if not query:
            return

        from ...services import QueryService

        service = QueryService()
        service._save_to_history(app.current_config.name, query)

    def on_focus_change(self, app: "SSMSTUI", widget: Any) -> None:
        """Handle focus changes - exit INSERT mode when leaving query input."""
        if not self.enabled:
            return

        has_query_focus = app.query_input.has_focus

        # Auto-exit INSERT mode when leaving query
        if not has_query_focus and app.editor_mode == VimMode.INSERT:
            app.editor_mode = VimMode.NORMAL
            app.query_input.read_only = True

    def get_leader_commands(self) -> list[LeaderCommand]:
        """Provide the vim toggle leader command."""
        return [
            LeaderCommand(
                key="v",
                action="toggle_vim_mode",
                label="Toggle Vim Mode",
                category="Actions",
            )
        ]

    def get_settings_defaults(self) -> dict[str, Any]:
        """Default settings for vim mode."""
        return {"vim_enabled": False}

    def on_settings_load(self, app: "SSMSTUI", settings: dict[str, Any]) -> None:
        """Load vim enabled state from settings."""
        self.enabled = settings.get("vim_enabled", False)

        if self.enabled:
            app.editor_mode = VimMode.NORMAL
            app.query_input.read_only = True

    def on_settings_save(self, app: "SSMSTUI", settings: dict[str, Any]) -> None:
        """Save vim enabled state to settings."""
        settings["vim_enabled"] = self.enabled

    def toggle(self, app: "SSMSTUI") -> None:
        """Toggle vim mode on/off and persist the setting."""
        from ...config import load_settings, save_settings

        self.enabled = not self.enabled

        # Persist the setting
        settings = load_settings()
        settings["vim_enabled"] = self.enabled
        save_settings(settings)

        if self.enabled:
            app.editor_mode = VimMode.NORMAL
            app.query_input.read_only = True
            if self.engine:
                self.engine.exit_insert_mode()
            app.notify("Editor: Vim")
        else:
            app.editor_mode = VimMode.INSERT
            app.query_input.read_only = False
            app.notify("Editor: Default")

        app._update_status_bar()
        app._update_footer_bindings()
