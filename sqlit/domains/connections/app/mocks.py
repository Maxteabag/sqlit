"""Mock profiles for demo recordings and testing."""

from __future__ import annotations

from .mock_adapter_core import MockConnection, MockCursor, MockDatabaseAdapter
from .mock_default_adapters import (
    DEFAULT_MOCK_ADAPTERS,
    create_default_mysql_adapter,
    create_default_postgresql_adapter,
    create_default_sqlite_adapter,
    create_default_supabase_adapter,
    get_default_mock_adapter,
)
from .mock_profiles import MOCK_PROFILES, MockProfile, get_mock_profile, list_mock_profiles
from .mock_provider import build_mock_provider

__all__ = [
    "DEFAULT_MOCK_ADAPTERS",
    "MOCK_PROFILES",
    "MockConnection",
    "MockCursor",
    "MockDatabaseAdapter",
    "MockProfile",
    "build_mock_provider",
    "create_default_mysql_adapter",
    "create_default_postgresql_adapter",
    "create_default_sqlite_adapter",
    "create_default_supabase_adapter",
    "get_default_mock_adapter",
    "get_mock_profile",
    "list_mock_profiles",
]
