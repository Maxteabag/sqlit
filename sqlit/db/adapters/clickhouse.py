"""ClickHouse adapter for real-time analytics database."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import ColumnInfo, DatabaseAdapter, IndexInfo, SequenceInfo, TableInfo, TriggerInfo

if TYPE_CHECKING:
    from ...config import ConnectionConfig


class ClickHouseAdapter(DatabaseAdapter):
    """Adapter for ClickHouse analytics database.

    ClickHouse is a column-oriented OLAP database designed for real-time analytics.
    It uses its own SQL dialect with some differences from standard SQL:
    - No traditional schemas - uses databases directly
    - No stored procedures
    - Uses backticks for identifier quoting (like MySQL)
    - System tables provide metadata (system.databases, system.tables, system.columns)
    """

    @property
    def name(self) -> str:
        return "ClickHouse"

    @property
    def install_extra(self) -> str:
        return "clickhouse"

    @property
    def install_package(self) -> str:
        return "clickhouse-connect"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("clickhouse_connect",)

    @property
    def supports_multiple_databases(self) -> bool:
        return True

    @property
    def supports_stored_procedures(self) -> bool:
        # ClickHouse doesn't have traditional stored procedures
        return False

    @property
    def supports_triggers(self) -> bool:
        # ClickHouse doesn't support triggers
        return False

    @property
    def supports_indexes(self) -> bool:
        # ClickHouse has data skipping indexes, but they work differently
        # than traditional indexes - we'll expose them anyway
        return True

    def execute_test_query(self, conn: Any) -> None:
        """Execute a simple query to verify the connection works.

        clickhouse-connect uses query() method, not cursors.
        """
        conn.query(self.test_query)

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to ClickHouse database.

        Uses clickhouse-connect which provides an HTTP interface to ClickHouse.
        This is generally easier to set up than the native TCP protocol.
        """
        try:
            import clickhouse_connect
        except ImportError as e:
            from ...db.exceptions import MissingDriverError

            if not self.install_extra or not self.install_package:
                raise e
            raise MissingDriverError(self.name, self.install_extra, self.install_package) from e

        # Default to port 8123 (HTTP interface) if not specified
        port = int(config.port) if config.port else 8123

        # Determine if we should use HTTPS based on port
        # 8443 is the standard HTTPS port for ClickHouse
        secure = port == 8443

        client = clickhouse_connect.get_client(
            host=config.server,
            port=port,
            username=config.username or "default",
            password=config.password or "",
            database=config.database or "default",
            secure=secure,
        )
        return client

    def get_databases(self, conn: Any) -> list[str]:
        """Get list of databases from ClickHouse."""
        result = conn.query("SELECT name FROM system.databases ORDER BY name")
        return [row[0] for row in result.result_rows]

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables from ClickHouse.

        Returns (database, table_name) tuples. ClickHouse doesn't have schemas
        within databases, so we use database as the "schema" for consistency.
        """
        if database:
            result = conn.query(
                "SELECT database, name FROM system.tables "
                "WHERE database = {db:String} "
                "AND engine NOT IN ('View', 'MaterializedView', 'LiveView', 'WindowView') "
                "ORDER BY name",
                parameters={"db": database},
            )
        else:
            # Get tables from current database
            result = conn.query(
                "SELECT database, name FROM system.tables "
                "WHERE database = currentDatabase() "
                "AND engine NOT IN ('View', 'MaterializedView', 'LiveView', 'WindowView') "
                "ORDER BY name"
            )
        return [(row[0], row[1]) for row in result.result_rows]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of views from ClickHouse.

        Views in ClickHouse are stored in system.tables with engine = 'View'.
        MaterializedViews are also included as they're a common ClickHouse pattern.
        """
        if database:
            result = conn.query(
                "SELECT database, name FROM system.tables "
                "WHERE database = {db:String} "
                "AND engine IN ('View', 'MaterializedView', 'LiveView', 'WindowView') "
                "ORDER BY name",
                parameters={"db": database},
            )
        else:
            result = conn.query(
                "SELECT database, name FROM system.tables "
                "WHERE database = currentDatabase() "
                "AND engine IN ('View', 'MaterializedView', 'LiveView', 'WindowView') "
                "ORDER BY name"
            )
        return [(row[0], row[1]) for row in result.result_rows]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get columns for a table from ClickHouse.

        ClickHouse doesn't have traditional schemas, so we use database directly.
        The schema parameter is treated as database for consistency with other adapters.
        """
        # Use schema as database if provided, otherwise fall back to database param
        db = schema or database

        if db:
            result = conn.query(
                "SELECT name, type, is_in_primary_key "
                "FROM system.columns "
                "WHERE database = {db:String} AND table = {tbl:String} "
                "ORDER BY position",
                parameters={"db": db, "tbl": table},
            )
        else:
            result = conn.query(
                "SELECT name, type, is_in_primary_key "
                "FROM system.columns "
                "WHERE database = currentDatabase() AND table = {tbl:String} "
                "ORDER BY position",
                parameters={"tbl": table},
            )

        return [
            ColumnInfo(
                name=row[0],
                data_type=row[1],
                is_primary_key=bool(row[2]),
            )
            for row in result.result_rows
        ]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """ClickHouse doesn't support stored procedures - return empty list."""
        return []

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        """Get data skipping indexes from ClickHouse.

        ClickHouse uses data skipping indexes (minmax, set, bloom_filter, etc.)
        rather than traditional B-tree indexes. These are stored in system.data_skipping_indices.
        """
        if database:
            result = conn.query(
                "SELECT name, table, type "
                "FROM system.data_skipping_indices "
                "WHERE database = {db:String} "
                "ORDER BY table, name",
                parameters={"db": database},
            )
        else:
            result = conn.query(
                "SELECT name, table, type "
                "FROM system.data_skipping_indices "
                "WHERE database = currentDatabase() "
                "ORDER BY table, name"
            )
        return [
            IndexInfo(name=row[0], table_name=row[1], is_unique=False)
            for row in result.result_rows
        ]

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        """ClickHouse doesn't support triggers - return empty list."""
        return []

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        """ClickHouse doesn't support sequences - return empty list."""
        return []

    def quote_identifier(self, name: str) -> str:
        """Quote identifier using backticks for ClickHouse.

        ClickHouse uses backticks like MySQL for identifier quoting.
        Escapes embedded backticks by doubling them.
        """
        escaped = name.replace("`", "``")
        return f"`{escaped}`"

    def build_select_query(
        self, table: str, limit: int, database: str | None = None, schema: str | None = None
    ) -> str:
        """Build SELECT LIMIT query for ClickHouse.

        ClickHouse uses standard LIMIT syntax.
        """
        # Use schema as database if provided
        db = schema or database
        quoted_table = self.quote_identifier(table)
        if db:
            quoted_db = self.quote_identifier(db)
            return f"SELECT * FROM {quoted_db}.{quoted_table} LIMIT {limit}"
        return f"SELECT * FROM {quoted_table} LIMIT {limit}"

    def execute_query(
        self, conn: Any, query: str, max_rows: int | None = None
    ) -> tuple[list[str], list[tuple], bool]:
        """Execute a query on ClickHouse with optional row limit.

        clickhouse-connect returns results differently than cursor-based adapters,
        so we implement this directly rather than using CursorBasedAdapter.
        """
        # If we have a row limit, modify the query to add LIMIT if not present
        # This is more efficient than fetching all rows and truncating
        modified_query = query
        truncated = False

        if max_rows is not None:
            query_upper = query.upper().strip()
            # Only add limit for SELECT queries that don't already have one
            if query_upper.startswith("SELECT") and "LIMIT" not in query_upper:
                # Fetch one extra to detect truncation
                modified_query = f"{query.rstrip().rstrip(';')} LIMIT {max_rows + 1}"

        result = conn.query(modified_query)

        if result.column_names:
            columns = list(result.column_names)
            rows = result.result_rows

            if max_rows is not None and len(rows) > max_rows:
                truncated = True
                rows = rows[:max_rows]

            return columns, [tuple(row) for row in rows], truncated

        return [], [], False

    def execute_non_query(self, conn: Any, query: str) -> int:
        """Execute a non-query on ClickHouse (INSERT, ALTER, etc.).

        ClickHouse doesn't return row counts for most operations,
        so we return -1 to indicate unknown affected rows.
        """
        conn.command(query)
        # ClickHouse command() doesn't return row count
        return -1
