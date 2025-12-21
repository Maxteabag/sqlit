"""Turso adapter using libsql-client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import ColumnInfo, DatabaseAdapter, IndexInfo, SequenceInfo, TableInfo, TriggerInfo, import_driver_module

if TYPE_CHECKING:
    from ...config import ConnectionConfig


class TursoAdapter(DatabaseAdapter):
    """Adapter for Turso (libSQL) databases.

    Turso is a distributed SQLite-compatible database. Uses the libsql_client
    package for connections via HTTP/HTTPS URLs with optional token authentication.
    """

    @property
    def name(self) -> str:
        return "Turso"

    @property
    def install_extra(self) -> str:
        return "turso"

    @property
    def install_package(self) -> str:
        return "libsql-client"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("libsql_client",)

    @property
    def supports_multiple_databases(self) -> bool:
        return False

    @property
    def supports_stored_procedures(self) -> bool:
        return False

    def execute_test_query(self, conn: Any) -> None:
        """Execute a simple query to verify the connection works.

        Turso uses a different API (no cursor, direct execute on connection).
        """
        conn.execute(self.test_query)

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to Turso database.

        Uses config.server for the database URL and config.password for the auth token.
        Supports libsql://, https://, and http:// URLs.
        """
        libsql_client = import_driver_module(
            "libsql_client",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        url = config.server
        # Ensure URL has proper scheme
        if not url.startswith(("libsql://", "https://", "http://")):
            url = f"libsql://{url}"

        auth_token = config.password if config.password else None
        client = libsql_client.create_client_sync(url, auth_token=auth_token)
        return client

    def get_databases(self, conn: Any) -> list[str]:
        """Turso doesn't support multiple databases - return empty list."""
        return []

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables from Turso. Returns (schema, name) with empty schema."""
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_litestream_%' "
            "ORDER BY name"
        )
        return [("", row[0]) for row in result.rows]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of views from Turso. Returns (schema, name) with empty schema."""
        result = conn.execute("SELECT name FROM sqlite_master WHERE type='view' ORDER BY name")
        return [("", row[0]) for row in result.rows]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get columns for a table from Turso. Schema parameter is ignored."""
        quoted_table = self.quote_identifier(table)
        result = conn.execute(f"PRAGMA table_info({quoted_table})")
        # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
        # pk > 0 indicates column is part of primary key
        return [ColumnInfo(name=row[1], data_type=row[2] or "TEXT", is_primary_key=row[5] > 0) for row in result.rows]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """Turso doesn't support stored procedures - return empty list."""
        return []

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        """Get indexes from Turso (SQLite-compatible)."""
        result = conn.execute(
            "SELECT name, tbl_name FROM sqlite_master "
            "WHERE type='index' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY tbl_name, name"
        )
        results = []
        for row in result.rows:
            # Check if index is unique using PRAGMA
            idx_result = conn.execute(f"PRAGMA index_list({self.quote_identifier(row[1])})")
            is_unique = False
            for idx_info in idx_result.rows:
                if idx_info[1] == row[0]:  # idx_info: seq, name, unique, origin, partial
                    is_unique = idx_info[2] == 1
                    break
            results.append(IndexInfo(name=row[0], table_name=row[1], is_unique=is_unique))
        return results

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        """Get triggers from Turso (SQLite-compatible)."""
        result = conn.execute(
            "SELECT name, tbl_name FROM sqlite_master "
            "WHERE type='trigger' "
            "ORDER BY tbl_name, name"
        )
        return [TriggerInfo(name=row[0], table_name=row[1]) for row in result.rows]

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        """Turso/SQLite doesn't support sequences - return empty list."""
        return []

    def quote_identifier(self, name: str) -> str:
        """Quote identifier using double quotes for Turso/SQLite.

        Escapes embedded double quotes by doubling them.
        """
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        """Build SELECT LIMIT query for Turso. Schema parameter is ignored."""
        return f'SELECT * FROM "{table}" LIMIT {limit}'

    def execute_query(self, conn: Any, query: str, max_rows: int | None = None) -> tuple[list[str], list[tuple], bool]:
        """Execute a query on Turso with optional row limit."""
        result = conn.execute(query)
        if result.columns:
            columns = list(result.columns)
            rows = [tuple(row) for row in result.rows]
            if max_rows is not None and len(rows) > max_rows:
                return columns, rows[:max_rows], True
            return columns, rows, False
        return [], [], False

    def execute_non_query(self, conn: Any, query: str) -> int:
        """Execute a non-query on Turso."""
        result = conn.execute(query)
        return int(result.rows_affected or 0)
