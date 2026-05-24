"""osquery adapter using osquery-python."""

from __future__ import annotations

import platform
from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.adapters.base import (
    ColumnInfo,
    DatabaseAdapter,
    IndexInfo,
    SequenceInfo,
    TableInfo,
    TriggerInfo,
)

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


class OsqueryConnection:
    """Wrapper for osquery connection that provides a consistent interface."""

    def __init__(self, instance: Any, is_spawned: bool = False) -> None:
        self.instance = instance
        self.is_spawned = is_spawned
        self._client: Any = None

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = self.instance.client
        return self._client

    def close(self) -> None:
        if self.is_spawned:
            # SpawnInstance doesn't need explicit close
            pass
        else:
            self.instance.close()


class OsqueryAdapter(DatabaseAdapter):
    """Adapter for osquery using osquery-python.

    osquery is not a traditional database - it queries system information
    through virtual tables. Supports both spawning an embedded instance
    and connecting to a running osqueryd daemon via socket.
    """

    @property
    def name(self) -> str:
        return "osquery"

    @property
    def install_extra(self) -> str:
        return "osquery"

    @property
    def install_package(self) -> str:
        return "osquery"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("osquery",)

    @property
    def supports_multiple_databases(self) -> bool:
        return False

    @property
    def supports_cross_database_queries(self) -> bool:
        return False

    @property
    def supports_stored_procedures(self) -> bool:
        return False

    @property
    def supports_indexes(self) -> bool:
        return False

    @property
    def supports_triggers(self) -> bool:
        return False

    @property
    def supports_sequences(self) -> bool:
        return False

    @property
    def supports_process_worker(self) -> bool:
        # osquery spawned instances may not work well across process boundaries
        return False

    @property
    def default_schema(self) -> str:
        return ""

    @property
    def test_query(self) -> str:
        return "SELECT 1 AS test"

    def execute_test_query(self, conn: Any) -> None:
        """Execute a simple query to verify the connection works."""
        result = conn.client.query("SELECT 1 AS test")
        if result.status.code != 0:
            raise Exception(f"osquery test failed: {result.status.message}")

    def _get_default_socket_path(self) -> str:
        """Get the default osquery socket path for the current platform."""
        if platform.system() == "Windows":
            return r"\\.\pipe\osquery.em"
        return "/var/osquery/osquery.em"

    def connect(self, config: ConnectionConfig) -> OsqueryConnection:
        osquery_module = self._import_driver_module(
            "osquery",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        connection_mode = str(config.get_option("connection_mode", "spawn"))

        if connection_mode == "socket":
            socket_path = config.get_option("socket_path")
            if not socket_path:
                socket_path = self._get_default_socket_path()
            instance = osquery_module.ExtensionClient(socket_path)
            instance.open()
            return OsqueryConnection(instance, is_spawned=False)
        else:
            # Spawn embedded instance. Accept an optional `binary_path` config
            # option so users can point at a portable osqueryd (e.g. installed
            # in ~/.local/bin) rather than the SDK's hardcoded /usr/bin/osqueryd.
            binary_path = config.get_option("binary_path")
            if binary_path:
                instance = osquery_module.SpawnInstance(path=str(binary_path))
            else:
                instance = osquery_module.SpawnInstance()
            instance.open()
            return OsqueryConnection(instance, is_spawned=True)

    def disconnect(self, conn: Any) -> None:
        if isinstance(conn, OsqueryConnection):
            conn.close()

    def get_databases(self, conn: Any) -> list[str]:
        # osquery has a single virtual database
        return ["main"]

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of osquery virtual tables."""
        result = conn.client.query(
            "SELECT name FROM osquery_registry WHERE registry = 'table' ORDER BY name"
        )
        if result.status.code != 0:
            return []
        return [("", row.get("name", "")) for row in result.response if row.get("name")]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        # osquery doesn't have views
        return []

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get column information for an osquery table using PRAGMA."""
        result = conn.client.query(f"PRAGMA table_info({table})")
        if result.status.code != 0:
            return []
        columns = []
        for row in result.response:
            name = row.get("name", "")
            data_type = row.get("type", "TEXT")
            if name:
                columns.append(ColumnInfo(name=name, data_type=data_type))
        return columns

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        return []

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        return []

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        return []

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        return []

    def quote_identifier(self, name: str) -> str:
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def build_select_query(
        self, table: str, limit: int, database: str | None = None, schema: str | None = None
    ) -> str:
        return f'SELECT * FROM "{table}" LIMIT {limit}'

    def execute_query(
        self, conn: Any, query: str, max_rows: int | None = None
    ) -> tuple[list[str], list[tuple], bool]:
        """Execute a query and return (columns, rows, truncated)."""
        result = conn.client.query(query)
        if result.status.code != 0:
            raise Exception(f"osquery error: {result.status.message}")

        if not result.response:
            return [], [], False

        # Get columns from first row
        first_row = result.response[0]
        columns = list(first_row.keys())

        # Convert rows to tuples
        all_rows = [tuple(row.get(col, None) for col in columns) for row in result.response]

        if max_rows is not None and len(all_rows) > max_rows:
            return columns, all_rows[:max_rows], True

        return columns, all_rows, False

    def execute_non_query(self, conn: Any, query: str) -> int:
        """Execute a non-query statement.

        osquery is read-only, so this just executes the query for compatibility.
        """
        result = conn.client.query(query)
        if result.status.code != 0:
            raise Exception(f"osquery error: {result.status.message}")
        return 0

    def classify_query(self, query: str) -> bool:
        """osquery queries are always SELECT-like (read-only)."""
        return True
