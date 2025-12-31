"""Mock profile definitions for demo and testing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.providers.adapters.base import ColumnInfo
from sqlit.domains.connections.providers.model import DatabaseProvider

from .mock_adapter_core import MockDatabaseAdapter
from .mock_default_adapters import (
    create_default_sqlite_adapter,
    create_default_supabase_adapter,
    get_default_mock_adapter,
)
from .mock_provider import build_mock_provider


@dataclass
class MockProfile:
    """A mock profile containing connections and adapter configuration."""

    name: str
    connections: list[ConnectionConfig] = field(default_factory=list)
    adapters: dict[str, MockDatabaseAdapter] = field(default_factory=dict)
    use_default_adapters: bool = True  # Use default adapters when profile doesn't define one
    query_delay: float = 0.0
    demo_rows: int = 0
    demo_long_text: bool = False
    _providers: dict[str, DatabaseProvider] = field(default_factory=dict, init=False, repr=False)

    def get_adapter(self, db_type: str) -> MockDatabaseAdapter:
        """Get adapter for a database type, falling back to defaults."""
        if db_type in self.adapters:
            adapter = self.adapters[db_type]
            adapter.apply_query_delay(self.query_delay)
            adapter.apply_demo_options(self.demo_rows, self.demo_long_text)
            return adapter
        if self.use_default_adapters:
            return get_default_mock_adapter(
                db_type,
                query_delay=self.query_delay,
                demo_rows=self.demo_rows,
                demo_long_text=self.demo_long_text,
            )
        return MockDatabaseAdapter(
            name=f"Mock{db_type.title()}",
            query_delay=self.query_delay,
            demo_rows=self.demo_rows,
            demo_long_text=self.demo_long_text,
        )

    def get_provider(self, db_type: str) -> DatabaseProvider:
        """Get provider for a database type, building one from mock adapters."""
        if db_type in self._providers:
            return self._providers[db_type]
        adapter = self.get_adapter(db_type)
        provider = build_mock_provider(db_type, adapter)
        self._providers[db_type] = provider
        return provider


def _create_sqlite_demo_profile() -> MockProfile:
    """Create the sqlite-demo profile with pre-configured connection."""
    connections = [
        ConnectionConfig.from_dict(
            {
                "name": "Demo SQLite",
                "db_type": "sqlite",
                "endpoint": {"kind": "file", "path": "./demo.db"},
            }
        ),
    ]

    return MockProfile(
        name="sqlite-demo",
        connections=connections,
        adapters={"sqlite": create_default_sqlite_adapter()},
        use_default_adapters=True,
    )


def _create_empty_profile() -> MockProfile:
    """Create an empty profile with no connections but default mock adapters."""
    return MockProfile(
        name="empty",
        connections=[],
        adapters={},
        use_default_adapters=True,  # Still use default mock adapters when connecting
    )


def _create_multi_db_profile() -> MockProfile:
    """Create a profile with multiple database types."""
    connections = [
        ConnectionConfig.from_dict(
            {
                "name": "Production PostgreSQL",
                "db_type": "postgresql",
                "endpoint": {
                    "kind": "tcp",
                    "host": "prod.example.com",
                    "port": "5432",
                    "database": "app_db",
                    "username": "admin",
                    "password": None,
                },
            }
        ),
        ConnectionConfig.from_dict(
            {
                "name": "Local SQLite",
                "db_type": "sqlite",
                "endpoint": {"kind": "file", "path": "./local.db"},
            }
        ),
        ConnectionConfig.from_dict(
            {
                "name": "Dev MySQL",
                "db_type": "mysql",
                "endpoint": {
                    "kind": "tcp",
                    "host": "localhost",
                    "port": "3306",
                    "database": "dev_db",
                    "username": "root",
                    "password": None,
                },
            }
        ),
    ]

    return MockProfile(
        name="multi-db",
        connections=connections,
        adapters={},
        use_default_adapters=True,
    )


def _create_driver_install_success_profile() -> MockProfile:
    """Profile intended for demoing the driver install UX."""
    connections = [
        ConnectionConfig.from_dict(
            {
                "name": "PostgreSQL (missing driver)",
                "db_type": "postgresql",
                "endpoint": {
                    "kind": "tcp",
                    "host": "localhost",
                    "port": "5432",
                    "database": "postgres",
                    "username": "user",
                    "password": None,
                },
            }
        ),
    ]
    return MockProfile(
        name="driver-install-success",
        connections=connections,
        adapters={},
        use_default_adapters=True,
    )


def _create_driver_install_fail_profile() -> MockProfile:
    """Profile intended for demoing the driver install failure UX."""
    connections = [
        ConnectionConfig.from_dict(
            {
                "name": "MySQL (missing driver)",
                "db_type": "mysql",
                "endpoint": {
                    "kind": "tcp",
                    "host": "localhost",
                    "port": "3306",
                    "database": "test_sqlit",
                    "username": "user",
                    "password": None,
                },
            }
        ),
    ]
    return MockProfile(
        name="driver-install-fail",
        connections=connections,
        adapters={},
        use_default_adapters=True,
    )


def _create_supabase_demo_profile() -> MockProfile:
    """Create a Supabase demo profile with empty connections but mock adapter."""
    return MockProfile(
        name="supabase-demo",
        connections=[],
        adapters={"supabase": create_default_supabase_adapter()},
        use_default_adapters=True,
    )


def _create_perf_test_profile() -> MockProfile:
    """Create a performance testing profile.

    Usage:
        sqlit --mock=perf-test --demo-rows=10000

    This profile is designed for testing DataTable rendering performance
    with large datasets. Use --demo-rows to specify the number of rows.
    """
    connections = [
        ConnectionConfig.from_dict(
            {
                "name": "Performance Test DB",
                "db_type": "sqlite",
                "endpoint": {"kind": "file", "path": "./perf_test.db"},
            }
        ),
    ]

    # Create an adapter that's optimized for perf testing
    # (minimal schema, fast responses)
    adapter = MockDatabaseAdapter(
        name="SQLite",
        tables=[
            ("main", "large_table"),
            ("main", "users"),
            ("main", "transactions"),
        ],
        views=[],
        columns={
            "large_table": [
                ColumnInfo("id", "INTEGER"),
                ColumnInfo("name", "TEXT"),
                ColumnInfo("email", "TEXT"),
                ColumnInfo("phone", "TEXT"),
                ColumnInfo("address", "TEXT"),
                ColumnInfo("created_at", "TEXT"),
            ],
            "users": [
                ColumnInfo("id", "INTEGER"),
                ColumnInfo("name", "TEXT"),
                ColumnInfo("email", "TEXT"),
            ],
            "transactions": [
                ColumnInfo("id", "INTEGER"),
                ColumnInfo("user_id", "INTEGER"),
                ColumnInfo("amount", "REAL"),
                ColumnInfo("timestamp", "TEXT"),
            ],
        },
        default_schema="main",
    )

    return MockProfile(
        name="perf-test",
        connections=connections,
        adapters={"sqlite": adapter},
        use_default_adapters=True,
    )


# Registry of available mock profiles
MOCK_PROFILES: dict[str, Callable[[], MockProfile]] = {
    "sqlite-demo": _create_sqlite_demo_profile,
    "empty": _create_empty_profile,
    "multi-db": _create_multi_db_profile,
    "driver-install-success": _create_driver_install_success_profile,
    "driver-install-fail": _create_driver_install_fail_profile,
    "supabase-demo": _create_supabase_demo_profile,
    "perf-test": _create_perf_test_profile,
}


def get_mock_profile(name: str) -> MockProfile | None:
    """Get a mock profile by name."""
    factory = MOCK_PROFILES.get(name)
    if factory:
        return factory()
    return None


def list_mock_profiles() -> list[str]:
    """List available mock profile names."""
    return list(MOCK_PROFILES.keys())
