"""Modal screens for sqlit."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = [
    "ConfirmScreen",
    "ConnectionScreen",
    "ConnectionPickerScreen",
    "DriverSetupScreen",
    "ErrorScreen",
    "HelpScreen",
    "LeaderMenuScreen",
    "MessageScreen",
    "PackageSetupScreen",
    "PasswordInputScreen",
    "QueryHistoryScreen",
    "ThemeScreen",
    "ValueViewScreen",
]

_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "ConfirmScreen": ("sqlit.ui.screens.confirm", "ConfirmScreen"),
    "ConnectionScreen": ("sqlit.ui.screens.connection", "ConnectionScreen"),
    "ConnectionPickerScreen": ("sqlit.ui.screens.connection_picker", "ConnectionPickerScreen"),
    "DriverSetupScreen": ("sqlit.ui.screens.driver_setup", "DriverSetupScreen"),
    "ErrorScreen": ("sqlit.ui.screens.error", "ErrorScreen"),
    "HelpScreen": ("sqlit.ui.screens.help", "HelpScreen"),
    "LeaderMenuScreen": ("sqlit.ui.screens.leader_menu", "LeaderMenuScreen"),
    "MessageScreen": ("sqlit.ui.screens.message", "MessageScreen"),
    "PackageSetupScreen": ("sqlit.ui.screens.package_setup", "PackageSetupScreen"),
    "PasswordInputScreen": ("sqlit.ui.screens.password_input", "PasswordInputScreen"),
    "QueryHistoryScreen": ("sqlit.ui.screens.query_history", "QueryHistoryScreen"),
    "ThemeScreen": ("sqlit.ui.screens.theme", "ThemeScreen"),
    "ValueViewScreen": ("sqlit.ui.screens.value_view", "ValueViewScreen"),
}

if TYPE_CHECKING:
    from .confirm import ConfirmScreen
    from .connection import ConnectionScreen
    from .connection_picker import ConnectionPickerScreen
    from .driver_setup import DriverSetupScreen
    from .error import ErrorScreen
    from .help import HelpScreen
    from .leader_menu import LeaderMenuScreen
    from .message import MessageScreen
    from .package_setup import PackageSetupScreen
    from .password_input import PasswordInputScreen
    from .query_history import QueryHistoryScreen
    from .theme import ThemeScreen
    from .value_view import ValueViewScreen


def __getattr__(name: str) -> Any:
    target = _LAZY_ATTRS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attr_name = target
    module = import_module(module_name)
    return getattr(module, attr_name)
