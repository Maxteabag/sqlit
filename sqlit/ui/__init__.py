"""UI components for sqlit."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = [
    "ConfirmScreen",
    "ConnectionScreen",
    "DriverSetupScreen",
    "HelpScreen",
    "QueryHistoryScreen",
    "ValueViewScreen",
]

_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "ConfirmScreen": ("sqlit.ui.screens.confirm", "ConfirmScreen"),
    "ConnectionScreen": ("sqlit.ui.screens.connection", "ConnectionScreen"),
    "DriverSetupScreen": ("sqlit.ui.screens.driver_setup", "DriverSetupScreen"),
    "HelpScreen": ("sqlit.ui.screens.help", "HelpScreen"),
    "QueryHistoryScreen": ("sqlit.ui.screens.query_history", "QueryHistoryScreen"),
    "ValueViewScreen": ("sqlit.ui.screens.value_view", "ValueViewScreen"),
}

if TYPE_CHECKING:
    from .screens.confirm import ConfirmScreen
    from .screens.connection import ConnectionScreen
    from .screens.driver_setup import DriverSetupScreen
    from .screens.help import HelpScreen
    from .screens.query_history import QueryHistoryScreen
    from .screens.value_view import ValueViewScreen


def __getattr__(name: str) -> Any:
    target = _LAZY_ATTRS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attr_name = target
    module = import_module(module_name)
    return getattr(module, attr_name)
