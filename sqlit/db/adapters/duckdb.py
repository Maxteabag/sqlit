"""DuckDB adapter for embedded analytics database."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import ColumnInfo, DatabaseAdapter, TableInfo, resolve_file_path

if TYPE_CHECKING:
    from ...config import ConnectionConfig


class DuckDBAdapter(DatabaseAdapter):
    """Adapter for DuckDB embedded database."""

    @property
    def name(self) -> str:
        return "DuckDB"

    @property
    def install_extra(self) -> str:
        return "duckdb"

    @property
    def install_package(self) -> str:
        return "duckdb"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("duckdb",)

    @property
    def supports_multiple_databases(self) -> bool:
        return False

    @property
    def supports_stored_procedures(self) -> bool:
        return False

    @property
    def default_schema(self) -> str:
        return "main"

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to DuckDB database file.

        Note: DuckDB connections have limited thread safety. Operations are
        serialized via exclusive workers to ensure only one thread accesses
        the connection at a time.
        """
        try:
            import duckdb
        except ImportError as e:
            from ...db.exceptions import MissingDriverError

            if not self.install_extra or not self.install_package:
                raise e
            raise MissingDriverError(self.name, self.install_extra, self.install_package) from e

        file_path = resolve_file_path(config.file_path)
        duckdb_any: Any = duckdb
        return duckdb_any.connect(str(file_path))

    def get_databases(self, conn: Any) -> list[str]:
        """DuckDB doesn't support multiple databases - return empty list."""
        return []

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables from DuckDB."""
        result = conn.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_type = 'BASE TABLE' "
            "AND table_schema NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY table_schema, table_name"
        )
        return [(row[0], row[1]) for row in result.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of views from DuckDB."""
        result = conn.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_type = 'VIEW' "
            "AND table_schema NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY table_schema, table_name"
        )
        return [(row[0], row[1]) for row in result.fetchall()]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get columns for a table from DuckDB."""
        schema = schema or "main"
        result = conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = ? AND table_name = ? "
            "ORDER BY ordinal_position",
            (schema, table),
        )
        return [ColumnInfo(name=row[0], data_type=row[1]) for row in result.fetchall()]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """DuckDB doesn't support stored procedures - return empty list."""
        return []

    def quote_identifier(self, name: str) -> str:
        """Quote identifier using double quotes for DuckDB.

        Escapes embedded double quotes by doubling them.
        """
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        """Build SELECT LIMIT query for DuckDB."""
        schema = schema or "main"
        return f'SELECT * FROM "{schema}"."{table}" LIMIT {limit}'

    def execute_query(self, conn: Any, query: str, max_rows: int | None = None) -> tuple[list[str], list[tuple], bool]:
        """Execute a query on DuckDB with optional row limit."""
        result = conn.execute(query)
        if result.description:
            columns = [col[0] for col in result.description]
            if max_rows is not None:
                rows = result.fetchmany(max_rows + 1)
                truncated = len(rows) > max_rows
                if truncated:
                    rows = rows[:max_rows]
            else:
                rows = result.fetchall()
                truncated = False
            return columns, [tuple(row) for row in rows], truncated
        return [], [], False

    def execute_non_query(self, conn: Any, query: str) -> int:
        """Execute a non-query on DuckDB."""
        result = conn.execute(query)
        # DuckDB doesn't provide rowcount for all operations
        try:
            return result.rowcount if hasattr(result, "rowcount") else -1
        except Exception:
            return -1
