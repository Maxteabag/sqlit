"""Plugin system for sqlit.

Plugins can extend sqlit with optional features like vim mode.
Each plugin is a self-contained module that registers hooks with the app.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..app import SSMSTUI


@dataclass
class LeaderCommand:
    """Definition of a leader command provided by a plugin."""

    key: str  # The key to press (e.g., "v")
    action: str  # The action name (e.g., "toggle_vim_mode")
    label: str  # Display label (e.g., "Toggle Vim Mode")
    category: str  # For grouping in menu ("Actions", "View", etc.)
    guard: str | None = None  # Optional guard function name


class Plugin(ABC):
    """Base class for sqlit plugins.

    Plugins extend sqlit with optional features. They:
    - Register themselves with the app at startup
    - Can intercept and handle key events
    - Can provide leader commands (<space>+key)
    - Can persist settings
    """

    name: str = "unnamed"  # Unique plugin identifier

    @abstractmethod
    def register(self, app: "SSMSTUI") -> None:
        """Called when app initializes. Set up the plugin here.

        Args:
            app: The main application instance
        """
        pass

    def on_key(self, app: "SSMSTUI", event: Any) -> bool:
        """Handle a key event.

        Args:
            app: The main application instance
            event: The key event from Textual

        Returns:
            True if the key was consumed, False to let it propagate
        """
        return False

    def on_focus_change(self, app: "SSMSTUI", widget: Any) -> None:
        """Called when focus changes in the app.

        Args:
            app: The main application instance
            widget: The newly focused widget
        """
        pass

    def get_leader_commands(self) -> list[LeaderCommand]:
        """Return leader commands this plugin provides.

        Returns:
            List of LeaderCommand definitions
        """
        return []

    def get_settings_defaults(self) -> dict[str, Any]:
        """Return default settings for this plugin.

        Returns:
            Dictionary of setting_name -> default_value
        """
        return {}

    def on_settings_load(self, app: "SSMSTUI", settings: dict[str, Any]) -> None:
        """Called when settings are loaded.

        Args:
            app: The main application instance
            settings: The loaded settings dictionary
        """
        pass

    def on_settings_save(self, app: "SSMSTUI", settings: dict[str, Any]) -> None:
        """Called before settings are saved. Modify settings dict to persist plugin state.

        Args:
            app: The main application instance
            settings: The settings dictionary to be saved
        """
        pass


# Plugin registry
_plugins: list[type[Plugin]] = []


def register_plugin(plugin_cls: type[Plugin]) -> type[Plugin]:
    """Decorator to register a plugin class.

    Usage:
        @register_plugin
        class MyPlugin(Plugin):
            ...
    """
    _plugins.append(plugin_cls)
    return plugin_cls


def discover_plugins() -> list[type[Plugin]]:
    """Discover and return all registered plugin classes.

    This imports plugin modules which triggers their @register_plugin decorators.

    Returns:
        List of plugin classes
    """
    # Import plugin modules to trigger registration
    try:
        from . import vim_mode  # noqa: F401
    except ImportError:
        pass

    return _plugins.copy()


def get_registered_plugins() -> list[type[Plugin]]:
    """Get already registered plugins without triggering discovery.

    Returns:
        List of registered plugin classes
    """
    return _plugins.copy()
