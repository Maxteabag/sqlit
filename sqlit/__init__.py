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

if TYPE_CHECKING:
    from .app import SSMSTUI
    from .cli import main
    from .config import AuthType, ConnectionConfig
    from importlib.metadata import PackageNotFoundError  # noqa: F401


_VERSION_CACHE: str | None = None


def _get_version() -> str:
    global _VERSION_CACHE
    if _VERSION_CACHE is not None:
        return _VERSION_CACHE
    try:
        from importlib.metadata import PackageNotFoundError, version

        _VERSION_CACHE = version("sqlit-tui")
    except PackageNotFoundError:
        # Package not installed (development mode without editable install)
        _VERSION_CACHE = "0.0.0.dev"
    return _VERSION_CACHE


def __getattr__(name: str) -> Any:
    """Lazy import for heavy modules to keep package import side-effect free."""
    if name == "__version__":
        return _get_version()
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
