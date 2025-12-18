"""Microsoft SQL Server adapter using pyodbc."""

from __future__ import annotations

import subprocess
import json
import struct

from typing import TYPE_CHECKING, Any
from datetime import datetime, timedelta, timezone

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
            return (
                base + f"Authentication=ActiveDirectoryPassword;"
                f"UID={config.username};PWD={config.password};"
            )
        elif auth == AuthType.AD_INTERACTIVE:
            return (
                base + f"Authentication=ActiveDirectoryInteractive;"
                f"UID={config.username};"
            )
        elif auth == AuthType.AD_INTEGRATED:
            return base + "Encrypt=yes;"
        return base + "Trusted_Connection=yes;"

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to SQL Server using pyodbc."""
        from ...config import AuthType

        try:
            import pyodbc
        except ImportError as e:
            from ...db.exceptions import MissingDriverError

            if not self.install_extra or not self.install_package:
                raise e
            raise MissingDriverError(
                self.name, self.install_extra, self.install_package
            ) from e

        installed = list(pyodbc.drivers())
        if config.driver not in installed:
            from ...db.exceptions import MissingODBCDriverError

            raise MissingODBCDriverError(config.driver, installed)

        conn_str = self._build_connection_string(config)

        # For AD_INTEGRATED, try Azure CLI token first
        if config.get_auth_type() == AuthType.AD_INTEGRATED:
            token = self._get_azure_cli_token()
            if token:
                # SQL_COPT_SS_ACCESS_TOKEN = 1256
                return pyodbc.connect(conn_str, attrs_before={1256: token}, timeout=10)
            # If token not available, fall back to standard integrated auth
            conn_str += "Authentication=ActiveDirectoryIntegrated;"

        connection = pyodbc.connect(conn_str, timeout=10)
        connection.add_output_converter(-155, self._handle_datetimeoffset)
        return connection

    def _handle_datetimeoffset(self, dto_value):
        # ref: https://github.com/mkleehammer/pyodbc/issues/134#issuecomment-281739794
        tup = struct.unpack(
            "<6hI2h", dto_value
        )  # e.g., (2017, 3, 16, 10, 35, 18, 500000000, -6, 0)
        return datetime(
            tup[0],
            tup[1],
            tup[2],
            tup[3],
            tup[4],
            tup[5],
            tup[6] // 1000,
            timezone(timedelta(hours=tup[7], minutes=tup[8])),
        )

    def _get_azure_cli_token(self) -> bytes | None:
        """Get Azure access token from Azure CLI.

        Returns:
                    Token bytes in the format pyodbc expects, or None if unavailable.
        """
        try:
            result = subprocess.run(
                [
                    "az",
                    "account",
                    "get-access-token",
                    "--resource",
                    "https://database.windows.net/",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            token = json.loads(result.stdout)["accessToken"]

            # Convert token to the format pyodbc expects (UTF-16-LE with length prefix)
            token_bytes = token.encode("utf-16-le")
            token_struct = struct.pack(
                f"<I{len(token_bytes)}s", len(token_bytes), token_bytes
            )
            return token_struct
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            FileNotFoundError,
            KeyError,
            json.JSONDecodeError,
        ):
            # Azure CLI not available, not logged in, or token retrieval failed
            return None

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
                "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.VIEWS "
                "ORDER BY TABLE_SCHEMA, TABLE_NAME"
            )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_columns(
        self,
        conn: Any,
        table: str,
        database: str | None = None,
        schema: str | None = None,
    ) -> list[ColumnInfo]:
        """Get columns for a table from SQL Server."""
        cursor = conn.cursor()
        schema = schema or "dbo"

        # Get primary key columns
        if database:
            cursor.execute(
                f"SELECT kcu.COLUMN_NAME "
                f"FROM [{database}].INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc "
                f"JOIN [{database}].INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu "
                f"  ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME "
                f"  AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA "
                f"WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY' "
                f"AND tc.TABLE_SCHEMA = ? AND tc.TABLE_NAME = ?",
                (schema, table),
            )
        else:
            cursor.execute(
                "SELECT kcu.COLUMN_NAME "
                "FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc "
                "JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu "
                "  ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME "
                "  AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA "
                "WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY' "
                "AND tc.TABLE_SCHEMA = ? AND tc.TABLE_NAME = ?",
                (schema, table),
            )
        pk_columns = {row[0] for row in cursor.fetchall()}

        # Get all columns
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
        return [
            ColumnInfo(
                name=row[0], data_type=row[1], is_primary_key=row[0] in pk_columns
            )
            for row in cursor.fetchall()
        ]

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

    def build_select_query(
        self,
        table: str,
        limit: int,
        database: str | None = None,
        schema: str | None = None,
    ) -> str:
        """Build SELECT TOP query for SQL Server."""
        schema = schema or "dbo"
        if database:
            return f"SELECT TOP {limit} * FROM [{database}].[{schema}].[{table}]"
        return f"SELECT TOP {limit} * FROM [{schema}].[{table}]"

    def execute_query(
        self, conn: Any, query: str, max_rows: int | None = None
    ) -> tuple[list[str], list[tuple], bool]:
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
