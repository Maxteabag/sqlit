"""Microsoft SQL Server adapter using mssql-python."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import ColumnInfo, DatabaseAdapter, IndexInfo, SequenceInfo, TableInfo, TriggerInfo, import_driver_module

if TYPE_CHECKING:
    from ...config import ConnectionConfig


class SQLServerAdapter(DatabaseAdapter):
    """Adapter for Microsoft SQL Server using the mssql-python driver."""

    @classmethod
    def badge_label(cls) -> str:
        return "MSSQL"

    @classmethod
    def url_schemes(cls) -> tuple[str, ...]:
        return ("mssql", "sqlserver")

    @property
    def name(self) -> str:
        return "SQL Server"

    @property
    def install_extra(self) -> str:
        return "mssql"

    @property
    def install_package(self) -> str:
        # Package providing the SQL Server driver (no external ODBC manager required)
        return "mssql-python"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        # DB-API 2.0 compatible driver
        return ("mssql_python",)

    @property
    def supports_multiple_databases(self) -> bool:
        return True

    @property
    def supports_stored_procedures(self) -> bool:
        return True

    def build_connection_string(self, config: ConnectionConfig) -> str:
        return self._build_connection_string(config)

    def get_auth_type(self, config: ConnectionConfig) -> "AuthType":
        from ...config import AuthType

        auth_type = config.get_option("auth_type", "sql")
        try:
            return AuthType(str(auth_type))
        except ValueError:
            return AuthType.SQL_SERVER

    def apply_database_override(self, config: ConnectionConfig, database: str) -> ConnectionConfig:
        from dataclasses import replace

        return replace(config, database=database) if database else config

    @property
    def default_schema(self) -> str:
        return "dbo"

    @property
    def supports_sequences(self) -> bool:
        """SQL Server 2012+ supports sequences."""
        return True

    @property
    def driver_setup_kind(self) -> str | None:
        # mssql-python uses Direct Database Connectivity and does not require
        # a separate ODBC driver manager.
        return None

    @classmethod
    def docker_image_patterns(cls) -> tuple[str, ...]:
        return ("mcr.microsoft.com/mssql", "mcr.microsoft.com/azure-sql-edge")

    @classmethod
    def docker_env_vars(cls) -> dict[str, tuple[str, ...]]:
        return {
            "user": (),
            "password": ("SA_PASSWORD", "MSSQL_SA_PASSWORD"),
            "database": (),
        }

    @classmethod
    def docker_default_user(cls) -> str | None:
        return "sa"

    @classmethod
    def docker_default_database(cls) -> str | None:
        return "master"

    def normalize_config(self, config: ConnectionConfig) -> ConnectionConfig:
        auth_type = str(config.get_option("auth_type") or "sql")
        config.set_option("auth_type", auth_type)

        trusted_connection = config.get_option("trusted_connection")
        if trusted_connection is None:
            config.set_option("trusted_connection", auth_type == "windows")

        if auth_type == "windows" and not config.get_option("trusted_connection") and config.username:
            config.set_option("auth_type", "sql")
            config.set_option("trusted_connection", False)

        return config

    def _build_connection_string(self, config: ConnectionConfig) -> str:
        """Build mssql-python connection string from config.

        Args:
            config: Connection configuration.

        Returns:
            semicolon-delimited key=value connection string.
        """
        from ...config import AuthType

        server_with_port = config.server
        if config.port and config.port != "1433":
            server_with_port = f"{config.server},{config.port}"

        base = (
            f"SERVER={server_with_port};"
            f"DATABASE={config.database or 'master'};"
            f"TrustServerCertificate=yes;"
        )

        auth = self.get_auth_type(config)

        if auth == AuthType.WINDOWS:
            return base + "Trusted_Connection=yes;"
        elif auth == AuthType.SQL_SERVER:
            return base + f"Authentication=SqlPassword;" f"UID={config.username};PWD={config.password};"
        elif auth == AuthType.AD_PASSWORD:
            return base + f"Authentication=ActiveDirectoryPassword;" f"UID={config.username};PWD={config.password};"
        elif auth == AuthType.AD_INTERACTIVE:
            return base + f"Authentication=ActiveDirectoryInteractive;" f"UID={config.username};"
        elif auth == AuthType.AD_INTEGRATED:
            return base + "Authentication=ActiveDirectoryIntegrated;"

        return base + "Trusted_Connection=yes;"

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to SQL Server using the mssql-python driver."""
        mssql_python = import_driver_module(
            "mssql_python",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        conn_str = self._build_connection_string(config)
        conn = mssql_python.connect(conn_str)

        # Store config and driver for potential reconnection to different databases
        conn._sqlit_config = config
        conn._sqlit_driver = mssql_python

        return conn

    def get_databases(self, conn: Any) -> list[str]:
        """Get list of databases from SQL Server."""
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sys.databases ORDER BY name")
        return [row[0] for row in cursor.fetchall()]

    def _get_cursor_for_database(self, conn: Any, database: str | None) -> Any:
        """Get a cursor for the specified database.

        For regular SQL Server: uses USE [database] to switch context.
        For Azure SQL Database: creates a new connection to the target database
        (since USE is not supported).

        Returns a cursor ready to execute queries against the target database.
        """
        cursor = conn.cursor()

        if not database:
            return cursor

        # First try USE (works on regular SQL Server, faster than reconnecting)
        try:
            cursor.execute(f"USE [{database}]")
            return cursor
        except Exception as e:
            error_msg = str(e).lower()
            if "use statement is not supported" not in error_msg and "switch between databases" not in error_msg:
                # Some other error - re-raise
                raise

        # Azure SQL Database: USE not supported, need a new connection
        # Check if we have the config stored for reconnection
        config = getattr(conn, "_sqlit_config", None)
        driver = getattr(conn, "_sqlit_driver", None)

        if config is None or driver is None:
            # No config available, can't reconnect - return original cursor
            # (will query the connected database instead)
            return cursor

        # Create a new connection with the target database
        from dataclasses import replace
        new_config = replace(config, database=database)
        new_conn_str = self._build_connection_string(new_config)

        try:
            new_conn = driver.connect(new_conn_str)
            new_cursor = new_conn.cursor()
            # Store reference to connection on cursor so it doesn't get garbage collected
            new_cursor._sqlit_temp_conn = new_conn
            return new_cursor
        except Exception:
            # Failed to connect to target database, fall back to original
            return cursor

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables with schema from SQL Server."""
        cursor = self._get_cursor_for_database(conn, database)
        cursor.execute(
            "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_SCHEMA, TABLE_NAME"
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of views with schema from SQL Server."""
        cursor = self._get_cursor_for_database(conn, database)
        cursor.execute(
            "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.VIEWS "
            "ORDER BY TABLE_SCHEMA, TABLE_NAME"
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get columns for a table from SQL Server."""
        cursor = self._get_cursor_for_database(conn, database)
        schema = schema or "dbo"

        # Get primary key columns
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
        cursor.execute(
            "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
            (schema, table),
        )
        return [ColumnInfo(name=row[0], data_type=row[1], is_primary_key=row[0] in pk_columns) for row in cursor.fetchall()]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """Get stored procedures from SQL Server."""
        cursor = self._get_cursor_for_database(conn, database)
        cursor.execute(
            "SELECT ROUTINE_NAME FROM INFORMATION_SCHEMA.ROUTINES "
            "WHERE ROUTINE_TYPE = 'PROCEDURE' ORDER BY ROUTINE_NAME"
        )
        return [row[0] for row in cursor.fetchall()]

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        """Get indexes from SQL Server."""
        cursor = self._get_cursor_for_database(conn, database)
        cursor.execute(
            "SELECT i.name, t.name, i.is_unique "
            "FROM sys.indexes i "
            "JOIN sys.tables t ON i.object_id = t.object_id "
            "WHERE i.name IS NOT NULL AND i.type > 0 AND i.is_primary_key = 0 "
            "ORDER BY t.name, i.name"
        )
        return [IndexInfo(name=row[0], table_name=row[1], is_unique=row[2]) for row in cursor.fetchall()]

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        """Get triggers from SQL Server."""
        cursor = self._get_cursor_for_database(conn, database)
        cursor.execute(
            "SELECT tr.name, OBJECT_NAME(tr.parent_id) "
            "FROM sys.triggers tr "
            "WHERE tr.is_ms_shipped = 0 AND tr.parent_id > 0 "
            "ORDER BY OBJECT_NAME(tr.parent_id), tr.name"
        )
        return [TriggerInfo(name=row[0], table_name=row[1] or "") for row in cursor.fetchall()]

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        """Get sequences from SQL Server (2012+)."""
        cursor = self._get_cursor_for_database(conn, database)
        cursor.execute("SELECT name FROM sys.sequences ORDER BY name")
        return [SequenceInfo(name=row[0]) for row in cursor.fetchall()]

    def get_index_definition(
        self, conn: Any, index_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a SQL Server index."""
        cursor = self._get_cursor_for_database(conn, database)
        cursor.execute(
            "SELECT i.is_unique, i.type_desc, c.name "
            "FROM sys.indexes i "
            "JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id "
            "JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id "
            "JOIN sys.tables t ON i.object_id = t.object_id "
            "WHERE i.name = ? AND t.name = ? "
            "ORDER BY ic.key_ordinal",
            (index_name, table_name),
        )
        rows = cursor.fetchall()
        is_unique = rows[0][0] if rows else False
        index_type = rows[0][1] if rows else "NONCLUSTERED"
        columns = [row[2] for row in rows]

        return {
            "name": index_name,
            "table_name": table_name,
            "columns": columns,
            "is_unique": is_unique,
            "type": index_type,
            "definition": f"CREATE {'UNIQUE ' if is_unique else ''}{index_type} INDEX [{index_name}] ON [{table_name}] ({', '.join(f'[{c}]' for c in columns)})",
        }

    def get_trigger_definition(
        self, conn: Any, trigger_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a SQL Server trigger."""
        cursor = self._get_cursor_for_database(conn, database)
        cursor.execute(
            "SELECT OBJECT_DEFINITION(tr.object_id), "
            "  CASE WHEN tr.is_instead_of_trigger = 1 THEN 'INSTEAD OF' "
            "       ELSE 'AFTER' END as timing "
            "FROM sys.triggers tr "
            "JOIN sys.tables t ON tr.parent_id = t.object_id "
            "WHERE tr.name = ? AND t.name = ?",
            (trigger_name, table_name),
        )
        row = cursor.fetchone()
        if row:
            definition = row[0]
            # Parse event from definition
            event = None
            if definition:
                upper_def = definition.upper()
                events = []
                if " INSERT" in upper_def:
                    events.append("INSERT")
                if " UPDATE" in upper_def:
                    events.append("UPDATE")
                if " DELETE" in upper_def:
                    events.append("DELETE")
                event = ", ".join(events) if events else None

            return {
                "name": trigger_name,
                "table_name": table_name,
                "timing": row[1],
                "event": event,
                "definition": definition,
            }
        return {
            "name": trigger_name,
            "table_name": table_name,
            "timing": None,
            "event": None,
            "definition": None,
        }

    def get_sequence_definition(
        self, conn: Any, sequence_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a SQL Server sequence."""
        cursor = self._get_cursor_for_database(conn, database)
        cursor.execute(
            "SELECT CAST(start_value AS BIGINT), CAST(increment AS BIGINT), "
            "CAST(minimum_value AS BIGINT), CAST(maximum_value AS BIGINT), is_cycling "
            "FROM sys.sequences WHERE name = ?",
            (sequence_name,),
        )
        row = cursor.fetchone()
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
