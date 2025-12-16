"""Microsoft SQL Server adapter using pyodbc."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import ColumnInfo, DatabaseAdapter, TableInfo

if TYPE_CHECKING:
    from ...config import ConnectionConfig


class SQLServerAdapter(DatabaseAdapter):
    """Adapter for Microsoft SQL Server using pyodbc."""

    @property
    def name(self) -> str:
        return "SQL Server"

    @property
    def install_extra(self) -> str:
        return "mssql"

    @property
    def install_package(self) -> str:
        return "pyodbc"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("pyodbc",)

    @property
    def supports_multiple_databases(self) -> bool:
        return True

    @property
    def supports_stored_procedures(self) -> bool:
        return True

    @property
    def default_schema(self) -> str:
        return "dbo"

    def _build_connection_string(self, config: ConnectionConfig) -> str:
        """Build ODBC connection string from config.

        This method encapsulates the SQL Server-specific connection string
        building logic that was previously in ConnectionConfig.get_connection_string().

        Args:
            config: Connection configuration.

        Returns:
            ODBC connection string for pyodbc.
        """
        from ...config import AuthType

        server_with_port = config.server
        if config.port and config.port != "1433":
            server_with_port = f"{config.server},{config.port}"

        base = (
            f"DRIVER={{{config.driver}}};"
            f"SERVER={server_with_port};"
            f"DATABASE={config.database or 'master'};"
            f"TrustServerCertificate=yes;"
        )

        auth = config.get_auth_type()

        if auth == AuthType.WINDOWS:
            return base + "Trusted_Connection=yes;"
        elif auth == AuthType.SQL_SERVER:
            return base + f"UID={config.username};PWD={config.password};"
        elif auth == AuthType.AD_PASSWORD:
            return base + f"Authentication=ActiveDirectoryPassword;" f"UID={config.username};PWD={config.password};"
        elif auth == AuthType.AD_INTERACTIVE:
            return base + f"Authentication=ActiveDirectoryInteractive;" f"UID={config.username};"
        elif auth == AuthType.AD_INTEGRATED:
            return base + "Authentication=ActiveDirectoryIntegrated;"

        return base + "Trusted_Connection=yes;"

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to SQL Server using pyodbc."""
        try:
            import pyodbc
        except ImportError as e:
            from ...db.exceptions import MissingDriverError

            if not self.install_extra or not self.install_package:
                raise e
            raise MissingDriverError(self.name, self.install_extra, self.install_package) from e

        installed = list(pyodbc.drivers())
        if config.driver not in installed:
            from ...db.exceptions import MissingODBCDriverError

            raise MissingODBCDriverError(config.driver, installed)

        conn_str = self._build_connection_string(config)
        return pyodbc.connect(conn_str, timeout=10)

    def get_databases(self, conn: Any) -> list[str]:
        """Get list of databases from SQL Server."""
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sys.databases ORDER BY name")
        return [row[0] for row in cursor.fetchall()]

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables with schema from SQL Server."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                f"SELECT TABLE_SCHEMA, TABLE_NAME FROM [{database}].INFORMATION_SCHEMA.TABLES "
                f"WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_SCHEMA, TABLE_NAME"
            )
        else:
            cursor.execute(
                "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_SCHEMA, TABLE_NAME"
            )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of views with schema from SQL Server."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                f"SELECT TABLE_SCHEMA, TABLE_NAME FROM [{database}].INFORMATION_SCHEMA.VIEWS "
                f"ORDER BY TABLE_SCHEMA, TABLE_NAME"
            )
        else:
            cursor.execute(
                "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.VIEWS " "ORDER BY TABLE_SCHEMA, TABLE_NAME"
            )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get columns for a table from SQL Server."""
        cursor = conn.cursor()
        schema = schema or "dbo"
        if database:
            cursor.execute(
                f"SELECT COLUMN_NAME, DATA_TYPE FROM [{database}].INFORMATION_SCHEMA.COLUMNS "
                f"WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
                (schema, table),
            )
        else:
            cursor.execute(
                "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
                (schema, table),
            )
        return [ColumnInfo(name=row[0], data_type=row[1]) for row in cursor.fetchall()]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """Get stored procedures from SQL Server."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                f"SELECT ROUTINE_NAME FROM [{database}].INFORMATION_SCHEMA.ROUTINES "
                f"WHERE ROUTINE_TYPE = 'PROCEDURE' ORDER BY ROUTINE_NAME"
            )
        else:
            cursor.execute(
                "SELECT ROUTINE_NAME FROM INFORMATION_SCHEMA.ROUTINES "
                "WHERE ROUTINE_TYPE = 'PROCEDURE' ORDER BY ROUTINE_NAME"
            )
        return [row[0] for row in cursor.fetchall()]

    def quote_identifier(self, name: str) -> str:
        """Quote identifier using SQL Server brackets.

        Escapes embedded ] by doubling them.
        """
        escaped = name.replace("]", "]]")
        return f"[{escaped}]"

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        """Build SELECT TOP query for SQL Server."""
        schema = schema or "dbo"
        if database:
            return f"SELECT TOP {limit} * FROM [{database}].[{schema}].[{table}]"
        return f"SELECT TOP {limit} * FROM [{schema}].[{table}]"

    def execute_query(self, conn: Any, query: str, max_rows: int | None = None) -> tuple[list[str], list[tuple], bool]:
        """Execute a query on SQL Server with optional row limit."""
        cursor = conn.cursor()
        cursor.execute(query)
        if cursor.description:
            columns = [col[0] for col in cursor.description]
            if max_rows is not None:
                rows = cursor.fetchmany(max_rows + 1)
                truncated = len(rows) > max_rows
                if truncated:
                    rows = rows[:max_rows]
            else:
                rows = cursor.fetchall()
                truncated = False
            return columns, [tuple(row) for row in rows], truncated
        return [], [], False

    def execute_non_query(self, conn: Any, query: str) -> int:
        """Execute a non-query on SQL Server."""
        cursor = conn.cursor()
        cursor.execute(query)
        rowcount = int(cursor.rowcount)
        conn.commit()
        return rowcount
