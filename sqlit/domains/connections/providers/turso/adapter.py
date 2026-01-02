"""Turso adapter using libsql."""

from __future__ import annotations

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


class TursoAdapter(DatabaseAdapter):
    """Adapter for Turso (libSQL) databases.

    Turso is a distributed SQLite-compatible database. Uses the libsql
    package for connections via HTTP/HTTPS URLs with optional token authentication.
    """

    @classmethod
    def normalize_docker_connection(cls, config: ConnectionConfig) -> ConnectionConfig:
        endpoint = config.tcp_endpoint
        if endpoint and endpoint.port and not endpoint.host.startswith(("http://", "https://", "libsql://")):
            config = config.with_endpoint(host=f"http://{endpoint.host}:{endpoint.port}", port="")
        return config

    def normalize_config(self, config: ConnectionConfig) -> ConnectionConfig:
        endpoint = config.tcp_endpoint
        if endpoint and endpoint.port:
            if endpoint.host.startswith(("http://", "https://", "libsql://")):
                config = config.with_endpoint(port="")
            elif ":" not in endpoint.host:
                config = config.with_endpoint(host=f"{endpoint.host}:{endpoint.port}", port="")
        return config

    @property
    def name(self) -> str:
        return "Turso"

    @property
    def install_extra(self) -> str:
        return "turso"

    @property
    def install_package(self) -> str:
        return "libsql"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("libsql",)

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

        Uses endpoint.host for the database URL and endpoint.password for the auth token.
        Accepts libsql://, https://, and http:// URLs (libsql:// is converted to https://).
        Uses direct HTTP mode for immediate read/write operations.
        """
        libsql = self._import_driver_module(
            "libsql",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        endpoint = config.tcp_endpoint
        if endpoint is None:
            raise ValueError("Turso connections require a TCP-style endpoint.")
        url = endpoint.host
        # Convert URL scheme (libsql package requires http:// or https://)
        if url.startswith("libsql://"):
            url = url.replace("libsql://", "https://", 1)
        elif not url.startswith(("https://", "http://")):
            url = f"https://{url}"

        auth_token = endpoint.password if endpoint.password else ""
        return libsql.connect(url, auth_token=auth_token)

    def get_databases(self, conn: Any) -> list[str]:
        """Turso doesn't support multiple databases - return empty list."""
        return []

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables from Turso. Returns (schema, name) with empty schema."""
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_litestream_%' "
            "ORDER BY name"
        ).fetchall()
        return [("", row[0]) for row in rows]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of views from Turso. Returns (schema, name) with empty schema."""
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='view' ORDER BY name").fetchall()
        return [("", row[0]) for row in rows]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get columns for a table from Turso. Schema parameter is ignored."""
        quoted_table = self.quote_identifier(table)
        rows = conn.execute(f"PRAGMA table_info({quoted_table})").fetchall()
        # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
        # pk > 0 indicates column is part of primary key
        return [ColumnInfo(name=row[1], data_type=row[2] or "TEXT", is_primary_key=row[5] > 0) for row in rows]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """Turso doesn't support stored procedures - return empty list."""
        return []

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        """Get indexes from Turso (SQLite-compatible)."""
        rows = conn.execute(
            "SELECT name, tbl_name FROM sqlite_master "
            "WHERE type='index' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY tbl_name, name"
        ).fetchall()
        results = []
        for row in rows:
            # Check if index is unique using PRAGMA
            idx_result = conn.execute(f"PRAGMA index_list({self.quote_identifier(row[1])})").fetchall()
            is_unique = False
            for idx_info in idx_result:
                if idx_info[1] == row[0]:  # idx_info: seq, name, unique, origin, partial
                    is_unique = idx_info[2] == 1
                    break
            results.append(IndexInfo(name=row[0], table_name=row[1], is_unique=is_unique))
        return results

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        """Get triggers from Turso (SQLite-compatible)."""
        rows = conn.execute(
            "SELECT name, tbl_name FROM sqlite_master "
            "WHERE type='trigger' "
            "ORDER BY tbl_name, name"
        ).fetchall()
        return [TriggerInfo(name=row[0], table_name=row[1]) for row in rows]

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
        cur = conn.cursor()
        rows = cur.execute(query).fetchall()
        columns = [col[0] for col in cur.description]
        if columns:
            rows = [tuple(row) for row in rows]
            if max_rows is not None and len(rows) > max_rows:
                return columns, rows[:max_rows], True
            return columns, rows, False
        return [], [], False

    def execute_non_query(self, conn: Any, query: str) -> int:
        """Execute a non-query on Turso."""
        cur = conn.cursor()
        cur.execute(query)
        rowcount = int(cur.rowcount or 0)
        conn.commit()
        return rowcount
