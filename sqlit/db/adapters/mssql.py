"""Microsoft SQL Server adapter using pyodbc."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import ColumnInfo, DatabaseAdapter, IndexInfo, SequenceInfo, TableInfo, TriggerInfo

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

    @property
    def supports_sequences(self) -> bool:
        """SQL Server 2012+ supports sequences."""
        return True

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
        return [ColumnInfo(name=row[0], data_type=row[1], is_primary_key=row[0] in pk_columns) for row in cursor.fetchall()]

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

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        """Get indexes from SQL Server."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                f"SELECT i.name, t.name, i.is_unique "
                f"FROM [{database}].sys.indexes i "
                f"JOIN [{database}].sys.tables t ON i.object_id = t.object_id "
                f"WHERE i.name IS NOT NULL AND i.type > 0 AND i.is_primary_key = 0 "
                f"ORDER BY t.name, i.name"
            )
        else:
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
        cursor = conn.cursor()
        if database:
            cursor.execute(
                f"SELECT tr.name, OBJECT_NAME(tr.parent_id, DB_ID('{database}')) "
                f"FROM [{database}].sys.triggers tr "
                f"WHERE tr.is_ms_shipped = 0 AND tr.parent_id > 0 "
                f"ORDER BY OBJECT_NAME(tr.parent_id, DB_ID('{database}')), tr.name"
            )
        else:
            cursor.execute(
                "SELECT tr.name, OBJECT_NAME(tr.parent_id) "
                "FROM sys.triggers tr "
                "WHERE tr.is_ms_shipped = 0 AND tr.parent_id > 0 "
                "ORDER BY OBJECT_NAME(tr.parent_id), tr.name"
            )
        return [TriggerInfo(name=row[0], table_name=row[1] or "") for row in cursor.fetchall()]

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        """Get sequences from SQL Server (2012+)."""
        cursor = conn.cursor()
        if database:
            cursor.execute(f"SELECT name FROM [{database}].sys.sequences ORDER BY name")
        else:
            cursor.execute("SELECT name FROM sys.sequences ORDER BY name")
        return [SequenceInfo(name=row[0]) for row in cursor.fetchall()]

    def get_index_definition(
        self, conn: Any, index_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a SQL Server index."""
        cursor = conn.cursor()
        # Get index info and columns
        if database:
            cursor.execute(
                f"SELECT i.is_unique, i.type_desc, c.name "
                f"FROM [{database}].sys.indexes i "
                f"JOIN [{database}].sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id "
                f"JOIN [{database}].sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id "
                f"JOIN [{database}].sys.tables t ON i.object_id = t.object_id "
                f"WHERE i.name = ? AND t.name = ? "
                f"ORDER BY ic.key_ordinal",
                (index_name, table_name),
            )
        else:
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
        cursor = conn.cursor()
        # Get trigger definition using OBJECT_DEFINITION
        if database:
            cursor.execute(
                f"SELECT OBJECT_DEFINITION(tr.object_id), "
                f"  CASE WHEN tr.is_instead_of_trigger = 1 THEN 'INSTEAD OF' "
                f"       ELSE 'AFTER' END as timing "
                f"FROM [{database}].sys.triggers tr "
                f"JOIN [{database}].sys.tables t ON tr.parent_id = t.object_id "
                f"WHERE tr.name = ? AND t.name = ?",
                (trigger_name, table_name),
            )
        else:
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
        cursor = conn.cursor()
        if database:
            cursor.execute(
                f"SELECT start_value, increment, minimum_value, maximum_value, is_cycling "
                f"FROM [{database}].sys.sequences WHERE name = ?",
                (sequence_name,),
            )
        else:
            cursor.execute(
                "SELECT start_value, increment, minimum_value, maximum_value, is_cycling "
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
