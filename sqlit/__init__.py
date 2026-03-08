"""sqlit - A terminal UI for SQL databases."""

__author__ = "Peter"

try:
    from ._version import __version__
except ImportError:
    __version__ = "0.0.0.dev"

__all__ = ["__version__"]
