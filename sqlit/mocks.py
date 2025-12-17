"""Mock profiles for demo recordings and testing.

Usage:
    sqlit --mock=sqlite-demo   # Pre-configured SQLite with demo data
    sqlit --mock=empty         # Empty connections, but mock adapters available
    sqlit --mock=multi-db      # Multiple database connections
    sqlit --mock=driver-install-success --mock-missing-drivers=postgresql --mock-install=success
    sqlit --mock=driver-install-fail --mock-missing-drivers=mysql --mock-install=fail
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .config import ConnectionConfig
from .db.adapters.base import ColumnInfo, DatabaseAdapter


class MockConnection:
    """Mock database connection object."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def cursor(self) -> MockCursor:
        return MockCursor()


class MockCursor:
    """Mock database cursor."""

    def __init__(self, results: list[tuple] | None = None, columns: list[str] | None = None):
        self._results = results or [(1, "Alice"), (2, "Bob")]
        self._columns = columns or ["id", "name"]
        self.description = [(c,) for c in self._columns]

    def execute(self, query: str, params: tuple = ()) -> None:
        pass

    def fetchall(self) -> list[tuple]:
        return self._results

    def fetchone(self) -> tuple | None:
        return self._results[0] if self._results else None

    def close(self) -> None:
        pass


class MockDatabaseAdapter(DatabaseAdapter):
    """Mock database adapter for demo/testing."""

    def __init__(
        self,
        name: str = "MockDB",
        tables: list[tuple[str, str]] | None = None,
        views: list[tuple[str, str]] | None = None,
        columns: dict[str, list[ColumnInfo]] | None = None,
        query_results: dict[str, tuple[list[str], list[tuple]]] | None = None,
        default_schema: str = "",
        default_query_result: tuple[list[str], list[tuple]] | None = None,
        connect_result: str = "success",
        connect_error: str = "Connection failed",
        required_fields: list[str] | None = None,
        allowed_connections: list[dict[str, Any]] | None = None,
        auth_error: str = "Authentication failed",
    ):
        self._name = name
        self._tables = tables or []
        self._views = views or []
        self._columns = columns or {}
        self._query_results = query_results or {}
        self._default_schema = default_schema
        self._default_query_result = default_query_result or (
            ["id", "name"],
            [(1, "Sample Row 1"), (2, "Sample Row 2")],
        )
        self._connect_result = (connect_result or "success").strip().lower()
        self._connect_error = connect_error or "Connection failed"
        self._required_fields = required_fields or []
        self._allowed_connections = allowed_connections or []
        self._auth_error = auth_error or "Authentication failed"

    @property
    def name(self) -> str:
        return self._name

    @property
    def default_schema(self) -> str:
        return self._default_schema

    @property
    def supports_multiple_databases(self) -> bool:
        return False

    @property
    def supports_stored_procedures(self) -> bool:
        return False

    def connect(self, config: ConnectionConfig) -> Any:
        if self._connect_result not in {"success", "ok", "pass"}:
            raise Exception(self._connect_error)

        if self._required_fields:
            missing = [field for field in self._required_fields if not getattr(config, field, None)]
            if missing:
                message = self._connect_error or f"Missing required fields: {', '.join(missing)}"
                raise Exception(message)

        if self._allowed_connections:
            if not any(_matches_connection_rule(config, rule) for rule in self._allowed_connections):
                raise Exception(self._auth_error)
        return MockConnection()

    def get_databases(self, conn: Any) -> list[str]:
        return []

    def get_tables(self, conn: Any, database: str | None = None) -> list[tuple[str, str]]:
        return self._tables

    def get_views(self, conn: Any, database: str | None = None) -> list[tuple[str, str]]:
        return self._views

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        if schema:
            return self._columns.get(f"{schema}.{table}", self._columns.get(table, []))
        return self._columns.get(table, [])

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        return []

    def quote_identifier(self, name: str) -> str:
        return f'"{name}"'

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        if schema:
            return f'SELECT * FROM "{schema}"."{table}" LIMIT {limit}'
        return f'SELECT * FROM "{table}" LIMIT {limit}'

    def execute_query(self, conn: Any, query: str, max_rows: int | None = None) -> tuple[list[str], list[tuple], bool]:
        """Execute a query and return (columns, rows, truncated)."""
        query_lower = query.lower().strip()

        # Check for specific query results (case-insensitive pattern matching)
        for pattern, result in self._query_results.items():
            if pattern.lower() in query_lower:
                cols, rows = result
                if max_rows and len(rows) > max_rows:
                    return cols, rows[:max_rows], True
                return cols, rows, False

        # Return default result for any other query
        cols, rows = self._default_query_result
        if max_rows and len(rows) > max_rows:
            return cols, rows[:max_rows], True
        return cols, rows, False

    def execute_non_query(self, conn: Any, query: str) -> int:
        return 1


# =============================================================================
# Default Mock Adapters - used when profiles don't define their own
# =============================================================================


def create_default_sqlite_adapter() -> MockDatabaseAdapter:
    """Create a default SQLite mock adapter with demo data."""
    return MockDatabaseAdapter(
        name="SQLite",
        tables=[
            ("main", "users"),
            ("main", "products"),
            ("main", "orders"),
        ],
        views=[],
        columns={
            "users": [
                ColumnInfo("id", "INTEGER"),
                ColumnInfo("name", "TEXT"),
                ColumnInfo("email", "TEXT"),
                ColumnInfo("created_at", "TEXT"),
            ],
            "products": [
                ColumnInfo("id", "INTEGER"),
                ColumnInfo("name", "TEXT"),
                ColumnInfo("price", "REAL"),
                ColumnInfo("stock", "INTEGER"),
            ],
            "orders": [
                ColumnInfo("id", "INTEGER"),
                ColumnInfo("user_id", "INTEGER"),
                ColumnInfo("product_id", "INTEGER"),
                ColumnInfo("quantity", "INTEGER"),
                ColumnInfo("created_at", "TEXT"),
            ],
        },
        query_results={
            # Patterns use just table name - matches both "SELECT * FROM users"
            # and schema-qualified 'SELECT * FROM "main"."users"'
            "users": (
                ["id", "name", "email", "created_at"],
                [
                    (1, "Alice Johnson", "alice@example.com", "2024-01-15"),
                    (2, "Bob Smith", "bob@example.com", "2024-01-16"),
                    (3, "Charlie Brown", "charlie@example.com", "2024-01-17"),
                ],
            ),
            "products": (
                ["id", "name", "price", "stock"],
                [
                    (1, "Widget", 9.99, 100),
                    (2, "Gadget", 19.99, 50),
                    (3, "Gizmo", 29.99, 25),
                ],
            ),
            "orders": (
                ["id", "user_id", "product_id", "quantity", "created_at"],
                [
                    (1, 1, 1, 2, "2024-01-20"),
                    (2, 1, 2, 1, "2024-01-21"),
                    (3, 2, 3, 3, "2024-01-22"),
                ],
            ),
        },
        default_schema="main",
        default_query_result=(
            ["result"],
            [("Query executed successfully",)],
        ),
    )


def create_default_postgresql_adapter() -> MockDatabaseAdapter:
    """Create a default PostgreSQL mock adapter."""
    return MockDatabaseAdapter(
        name="PostgreSQL",
        tables=[
            ("public", "users"),
            ("public", "accounts"),
        ],
        views=[],
        columns={
            "users": [
                ColumnInfo("id", "SERIAL"),
                ColumnInfo("username", "VARCHAR"),
                ColumnInfo("email", "VARCHAR"),
            ],
            "accounts": [
                ColumnInfo("id", "SERIAL"),
                ColumnInfo("user_id", "INTEGER"),
                ColumnInfo("balance", "NUMERIC"),
            ],
        },
        query_results={},
        default_schema="public",
    )


def create_default_mysql_adapter() -> MockDatabaseAdapter:
    """Create a default MySQL mock adapter."""
    return MockDatabaseAdapter(
        name="MySQL",
        tables=[
            ("", "customers"),
            ("", "orders"),
        ],
        views=[],
        columns={
            "customers": [
                ColumnInfo("id", "INT"),
                ColumnInfo("name", "VARCHAR"),
                ColumnInfo("email", "VARCHAR"),
            ],
        },
        query_results={},
        default_schema="",
    )


# Registry of default adapters by database type
DEFAULT_MOCK_ADAPTERS: dict[str, Callable[[], MockDatabaseAdapter]] = {
    "sqlite": create_default_sqlite_adapter,
    "postgresql": create_default_postgresql_adapter,
    "mysql": create_default_mysql_adapter,
}


def get_default_mock_adapter(db_type: str) -> MockDatabaseAdapter:
    """Get a default mock adapter for a database type."""
    factory = DEFAULT_MOCK_ADAPTERS.get(db_type)
    if factory:
        return factory()
    # Fallback for unknown types
    return MockDatabaseAdapter(name=f"Mock{db_type.title()}")


def _matches_connection_rule(config: ConnectionConfig, rule: dict[str, Any]) -> bool:
    for key, value in rule.items():
        if getattr(config, key, None) != value:
            return False
    return True


# =============================================================================
# Mock Profiles
# =============================================================================


@dataclass
class MockProfile:
    """A mock profile containing connections and adapter configuration."""

    name: str
    connections: list[ConnectionConfig] = field(default_factory=list)
    adapters: dict[str, MockDatabaseAdapter] = field(default_factory=dict)
    use_default_adapters: bool = True  # Use default adapters when profile doesn't define one

    def get_adapter(self, db_type: str) -> MockDatabaseAdapter:
        """Get adapter for a database type, falling back to defaults."""
        if db_type in self.adapters:
            return self.adapters[db_type]
        if self.use_default_adapters:
            return get_default_mock_adapter(db_type)
        return MockDatabaseAdapter(name=f"Mock{db_type.title()}")


def _create_sqlite_demo_profile() -> MockProfile:
    """Create the sqlite-demo profile with pre-configured connection."""
    connections = [
        ConnectionConfig(
            name="Demo SQLite",
            db_type="sqlite",
            file_path="./demo.db",
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
        ConnectionConfig(
            name="Production PostgreSQL",
            db_type="postgresql",
            server="prod.example.com",
            port="5432",
            database="app_db",
            username="admin",
        ),
        ConnectionConfig(
            name="Local SQLite",
            db_type="sqlite",
            file_path="./local.db",
        ),
        ConnectionConfig(
            name="Dev MySQL",
            db_type="mysql",
            server="localhost",
            port="3306",
            database="dev_db",
            username="root",
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
        ConnectionConfig(
            name="PostgreSQL (missing driver)",
            db_type="postgresql",
            server="localhost",
            port="5432",
            database="postgres",
            username="user",
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
        ConnectionConfig(
            name="MySQL (missing driver)",
            db_type="mysql",
            server="localhost",
            port="3306",
            database="test_sqlit",
            username="user",
        ),
    ]
    return MockProfile(
        name="driver-install-fail",
        connections=connections,
        adapters={},
        use_default_adapters=True,
    )


# Registry of available mock profiles
MOCK_PROFILES: dict[str, Callable[[], MockProfile]] = {
    "sqlite-demo": _create_sqlite_demo_profile,
    "empty": _create_empty_profile,
    "multi-db": _create_multi_db_profile,
    "driver-install-success": _create_driver_install_success_profile,
    "driver-install-fail": _create_driver_install_fail_profile,
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
