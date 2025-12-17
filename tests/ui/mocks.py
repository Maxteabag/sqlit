"""Mock implementations for UI testing.

These mocks allow testing UI workflows without real database connections.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlit.config import ConnectionConfig
from sqlit.db.adapters.base import ColumnInfo, DatabaseAdapter


class MockConnectionStore:
    """Mock connection store for testing."""

    def __init__(self, connections: list[ConnectionConfig] | None = None):
        self.connections = connections or []
        self.save_called = False
        self.last_saved: list[ConnectionConfig] = []

    def load_all(self, load_credentials: bool = True) -> list[ConnectionConfig]:
        return self.connections.copy()

    def save_all(self, connections: list[ConnectionConfig]) -> None:
        self.save_called = True
        self.last_saved = connections.copy()
        self.connections = connections.copy()

    def get_by_name(self, name: str) -> ConnectionConfig | None:
        for conn in self.connections:
            if conn.name == name:
                return conn
        return None

    def add(self, connection: ConnectionConfig) -> None:
        if any(c.name == connection.name for c in self.connections):
            raise ValueError(f"Connection '{connection.name}' already exists")
        self.connections.append(connection)
        self.save_called = True

    def delete(self, name: str) -> bool:
        original_count = len(self.connections)
        self.connections = [c for c in self.connections if c.name != name]
        if len(self.connections) < original_count:
            self.save_called = True
            return True
        return False

    def list_names(self) -> list[str]:
        return [c.name for c in self.connections]


class MockHistoryStore:
    """Mock history store for testing."""

    def __init__(self):
        self.entries: dict[str, list[dict]] = {}

    def load_for_connection(self, connection_name: str) -> list:
        return self.entries.get(connection_name, [])

    def save_query(self, connection_name: str, query: str) -> None:
        if connection_name not in self.entries:
            self.entries[connection_name] = []
        self.entries[connection_name].append({"query": query})

    def delete_entry(self, connection_name: str, timestamp: str) -> bool:
        return False

    def clear_for_connection(self, connection_name: str) -> int:
        count = len(self.entries.get(connection_name, []))
        self.entries[connection_name] = []
        return count


class MockSettingsStore:
    """Mock settings store for testing."""

    def __init__(self, settings: dict | None = None):
        self.settings = settings or {}

    def load_all(self) -> dict:
        return self.settings.copy()

    def save_all(self, settings: dict) -> None:
        self.settings = settings.copy()

    def get(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.settings[key] = value


class MockDatabaseAdapter(DatabaseAdapter):
    """Mock database adapter for testing.

    Simulates database operations without actual connections.
    """

    def __init__(
        self,
        name: str = "MockDB",
        tables: list[tuple[str, str]] | None = None,
        views: list[tuple[str, str]] | None = None,
        columns: dict[str, list[ColumnInfo]] | None = None,
        should_fail_connect: bool = False,
        connect_error: str = "Connection failed",
        default_schema: str = "",
    ):
        self._name = name
        self._tables = tables or [("", "users"), ("", "products")]
        self._views = views or [("", "user_summary")]
        self._columns = columns or {
            "users": [
                ColumnInfo("id", "INTEGER"),
                ColumnInfo("name", "VARCHAR"),
                ColumnInfo("email", "VARCHAR"),
            ],
            "products": [
                ColumnInfo("id", "INTEGER"),
                ColumnInfo("name", "VARCHAR"),
                ColumnInfo("price", "DECIMAL"),
            ],
        }
        self._should_fail_connect = should_fail_connect
        self._connect_error = connect_error
        self._connected = False
        self._executed_queries: list[str] = []
        self._default_schema = default_schema

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
        if self._should_fail_connect:
            raise ConnectionError(self._connect_error)
        self._connected = True
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
        return self._columns.get(table, [])

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        return []

    def quote_identifier(self, name: str) -> str:
        return f'"{name}"'

    def build_select_query(self, table: str, limit: int, database: str | None = None) -> str:
        return f'SELECT * FROM "{table}" LIMIT {limit}'

    def execute_query(self, conn: Any, query: str) -> tuple[list[str], list[tuple]]:
        self._executed_queries.append(query)
        # Return mock data
        return ["id", "name"], [(1, "Alice"), (2, "Bob")]

    def execute_non_query(self, conn: Any, query: str) -> int:
        self._executed_queries.append(query)
        return 1


class MockConnection:
    """Mock database connection object."""

    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    def cursor(self):
        return MockCursor()


class MockCursor:
    """Mock database cursor."""

    def __init__(self):
        self.description = [("id",), ("name",)]
        self._results = [(1, "Alice"), (2, "Bob")]

    def execute(self, query: str, params: tuple = ()) -> None:
        pass

    def fetchall(self) -> list[tuple]:
        return self._results

    def fetchone(self) -> tuple | None:
        return self._results[0] if self._results else None

    def close(self) -> None:
        pass


@dataclass
class MockAdapterRegistry:
    """Registry for mock adapters, replacing get_adapter()."""

    adapters: dict[str, MockDatabaseAdapter] = field(default_factory=dict)
    default_adapter: MockDatabaseAdapter | None = None

    def get_adapter(self, db_type: str) -> MockDatabaseAdapter:
        if db_type in self.adapters:
            return self.adapters[db_type]
        if self.default_adapter:
            return self.default_adapter
        return MockDatabaseAdapter(name=f"Mock{db_type.title()}")

    def register(self, db_type: str, adapter: MockDatabaseAdapter) -> None:
        self.adapters[db_type] = adapter


def create_test_connection(
    name: str = "test-connection",
    db_type: str = "sqlite",
    **kwargs,
) -> ConnectionConfig:
    """Helper to create test connection configs."""
    defaults = {
        "name": name,
        "db_type": db_type,
        "server": "localhost",
        "port": "5432",
        "database": "testdb",
        "username": "testuser",
        "password": "testpass",
        "file_path": "/tmp/test.db",
    }
    defaults.update(kwargs)
    return ConnectionConfig(**defaults)
