"""Core mock adapter implementations."""

from __future__ import annotations

import time
from typing import Any

from sqlit.domains.connections.providers.adapters.base import (
    ColumnInfo,
    DatabaseAdapter,
    IndexInfo,
    SequenceInfo,
    TriggerInfo,
)

from .mock_data import generate_fake_data, generate_long_text_data


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
        indexes: list[IndexInfo] | None = None,
        triggers: list[TriggerInfo] | None = None,
        sequences: list[SequenceInfo] | None = None,
        query_results: dict[str, tuple[list[str], list[tuple]]] | None = None,
        default_schema: str = "",
        default_query_result: tuple[list[str], list[tuple]] | None = None,
        connect_result: str = "success",
        connect_error: str = "Connection failed",
        required_fields: list[str] | None = None,
        allowed_connections: list[dict[str, Any]] | None = None,
        auth_error: str = "Authentication failed",
        query_delay: float = 0.0,
        demo_rows: int = 0,
        demo_long_text: bool = False,
    ):
        self._name = name
        self._tables = tables or []
        self._views = views or []
        self._columns = columns or {}
        self._indexes = indexes or []
        self._triggers = triggers or []
        self._sequences = sequences or []
        self._query_results = query_results or {}
        self._default_schema = default_schema
        self._default_query_result = default_query_result or (["result"], [("Mock result",)])
        self._connect_result = connect_result
        self._connect_error = connect_error
        self._required_fields = required_fields or []
        self._allowed_connections = allowed_connections or []
        self._auth_error = auth_error
        self._query_delay = query_delay
        self._demo_rows = demo_rows
        self._demo_long_text = demo_long_text

    @property
    def name(self) -> str:
        return self._name

    @property
    def supports_multiple_databases(self) -> bool:
        return True

    @property
    def supports_cross_database_queries(self) -> bool:
        return True

    @property
    def supports_stored_procedures(self) -> bool:
        return True

    @property
    def supports_indexes(self) -> bool:
        return True

    @property
    def supports_triggers(self) -> bool:
        return True

    @property
    def supports_sequences(self) -> bool:
        return True

    @property
    def default_schema(self) -> str:
        return self._default_schema

    @property
    def system_databases(self) -> frozenset[str]:
        return frozenset()

    def connect(self, config: Any) -> MockConnection:
        # Simulate connection failures based on configuration
        if self._connect_result == "fail":
            raise Exception(self._connect_error)

        # Check for required fields
        for field in self._required_fields:
            if not config.get_field_value(field):
                raise Exception(f"Missing required field: {field}")

        # Check allowed connections
        if self._allowed_connections:
            matched = False
            for rule in self._allowed_connections:
                if all(config.get_field_value(k) == v for k, v in rule.items()):
                    matched = True
                    break
            if not matched:
                raise Exception(self._auth_error)

        return MockConnection()

    def get_databases(self, conn: Any) -> list[str]:
        if self._default_schema:
            return [self._default_schema]
        return ["mockdb"]

    def get_tables(self, conn: Any, database: str | None = None) -> list[tuple[str, str]]:
        return list(self._tables)

    def get_views(self, conn: Any, database: str | None = None) -> list[tuple[str, str]]:
        return list(self._views)

    def get_columns(
        self,
        conn: Any,
        table: str,
        database: str | None = None,
        schema: str | None = None,
    ) -> list[ColumnInfo]:
        table_key = table
        if schema:
            schema_key = f"{schema}.{table}"
            if schema_key in self._columns:
                table_key = schema_key
        return list(self._columns.get(table_key, []))

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        return []

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        return list(self._indexes)

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        return list(self._triggers)

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        return list(self._sequences)

    def quote_identifier(self, name: str) -> str:
        return f'"{name}"'

    def build_select_query(
        self,
        table: str,
        limit: int,
        database: str | None = None,
        schema: str | None = None,
    ) -> str:
        parts = []
        if database:
            parts.append(self.quote_identifier(database))
        if schema:
            parts.append(self.quote_identifier(schema))
        parts.append(self.quote_identifier(table))
        target = ".".join(parts)
        return f"SELECT * FROM {target} LIMIT {limit}"

    def disconnect(self, conn: MockConnection) -> None:
        conn.close()

    def execute_query(self, conn: MockConnection, query: str, max_rows: int | None = None) -> tuple[list[str], list[tuple], bool]:
        if self._query_delay > 0:
            time.sleep(self._query_delay)

        # Check if demo long text mode is enabled (for testing truncation)
        demo_long_text = self._demo_long_text
        demo_rows = self._demo_rows

        if demo_long_text:
            demo_row_count = demo_rows or 10
            cols, rows = generate_long_text_data(demo_row_count)
            if max_rows and len(rows) > max_rows:
                return cols, rows[:max_rows], True
            return cols, rows, False

        # Check if demo rows mode is enabled
        if demo_rows > 0:
            cols, rows = generate_fake_data(demo_rows)
            if max_rows and len(rows) > max_rows:
                return cols, rows[:max_rows], True
            return cols, rows, False

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

    def apply_query_delay(self, delay: float) -> None:
        self._query_delay = delay

    def apply_demo_options(self, demo_rows: int = 0, demo_long_text: bool = False) -> None:
        self._demo_rows = demo_rows
        self._demo_long_text = demo_long_text
