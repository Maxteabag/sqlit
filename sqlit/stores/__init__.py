"""Data persistence stores for sqlit.

This package provides clean separation of data persistence concerns:
- ConnectionStore: manages saved database connections
- HistoryStore: manages query history per connection
- SettingsStore: manages application settings
"""

from .connections import ConnectionStore
from .history import HistoryStore
from .settings import SettingsStore
from .starred import StarredStore

__all__ = [
    "ConnectionStore",
    "HistoryStore",
    "SettingsStore",
    "StarredStore",
]
