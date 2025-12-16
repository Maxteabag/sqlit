"""sqlit - A terminal UI for SQL databases."""

from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

try:
    __version__ = version("sqlit-tui")
except PackageNotFoundError:
    # Package not installed (development mode without editable install)
    __version__ = "0.0.0.dev"

__author__ = "Peter"

__all__ = [
    "main",
    "SSMSTUI",
    "AuthType",
    "ConnectionConfig",
]

if TYPE_CHECKING:
    from .app import SSMSTUI
    from .cli import main
    from .config import AuthType, ConnectionConfig


def __getattr__(name: str) -> Any:
    """Lazy import for heavy modules to keep package import side-effect free."""
    if name == "main":
        from .cli import main

        return main
    if name == "SSMSTUI":
        from .app import SSMSTUI

        return SSMSTUI
    if name == "AuthType":
        from .config import AuthType

        return AuthType
    if name == "ConnectionConfig":
        from .config import ConnectionConfig

        return ConnectionConfig
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
