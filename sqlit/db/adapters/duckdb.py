"""DuckDB adapter for embedded analytics database."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import ColumnInfo, DatabaseAdapter, IndexInfo, SequenceInfo, TableInfo, TriggerInfo, resolve_file_path

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
    def supports_triggers(self) -> bool:
        """DuckDB doesn't support triggers (columnar/OLAP database)."""
        return False

    @property
    def supports_sequences(self) -> bool:
        """DuckDB supports sequences."""
        return True

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

        # Get primary key columns
        result = conn.execute(
            "SELECT kcu.column_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            "  AND tc.table_schema = kcu.table_schema "
            "WHERE tc.constraint_type = 'PRIMARY KEY' "
            "AND tc.table_schema = ? AND tc.table_name = ?",
            (schema, table),
        )
        pk_columns = {row[0] for row in result.fetchall()}

        # Get all columns
        result = conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = ? AND table_name = ? "
            "ORDER BY ordinal_position",
            (schema, table),
        )
        return [ColumnInfo(name=row[0], data_type=row[1], is_primary_key=row[0] in pk_columns) for row in result.fetchall()]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """DuckDB doesn't support stored procedures - return empty list."""
        return []

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        """Get indexes from DuckDB using duckdb_indexes() function."""
        result = conn.execute(
            "SELECT index_name, table_name, is_unique "
            "FROM duckdb_indexes() "
            "ORDER BY table_name, index_name"
        )
        return [
            IndexInfo(name=row[0], table_name=row[1], is_unique=row[2])
            for row in result.fetchall()
        ]

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        """DuckDB doesn't support triggers - return empty list."""
        return []

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        """Get sequences from DuckDB using duckdb_sequences() function."""
        result = conn.execute(
            "SELECT sequence_name FROM duckdb_sequences() ORDER BY sequence_name"
        )
        return [SequenceInfo(name=row[0]) for row in result.fetchall()]

    def get_index_definition(
        self, conn: Any, index_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a DuckDB index."""
        result = conn.execute(
            "SELECT is_unique, sql FROM duckdb_indexes() WHERE index_name = ?",
            (index_name,),
        )
        row = result.fetchone()
        if row:
            return {
                "name": index_name,
                "table_name": table_name,
                "columns": [],  # Would need to parse sql to extract
                "is_unique": row[0],
                "definition": row[1],
            }
        return {
            "name": index_name,
            "table_name": table_name,
            "columns": [],
            "is_unique": False,
            "definition": None,
        }

    def get_sequence_definition(
        self, conn: Any, sequence_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a DuckDB sequence."""
        result = conn.execute(
            "SELECT start_value, increment_by, min_value, max_value, cycle "
            "FROM duckdb_sequences() WHERE sequence_name = ?",
            (sequence_name,),
        )
        row = result.fetchone()
        if row:
            return {
                "name": sequence_name,
                "start_value": row[0],
                "increment": row[1],
                "min_value": row[2],
                "max_value": row[3],
                "cycle": row[4],
            }
        return {
            "name": sequence_name,
            "start_value": None,
            "increment": None,
            "min_value": None,
            "max_value": None,
            "cycle": None,
        }

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
