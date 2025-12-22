"""sqlit - A terminal UI for SQL databases."""

from typing import TYPE_CHECKING, Any

__author__ = "Peter"

__all__ = [
    "__version__",
    "main",
    "SSMSTUI",
    "AuthType",
    "ConnectionConfig",
]

try:
    from ._version import __version__
except ImportError:
    __version__ = "0.0.0.dev"

if TYPE_CHECKING:
    from .app import SSMSTUI
    from .cli import main
    from .config import AuthType, ConnectionConfig
    from importlib.metadata import PackageNotFoundError  # noqa: F401


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
