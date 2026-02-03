"""IBM DB2 for i adapter using pyodbc with ODBC driver."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.adapters.base import (
    ColumnInfo,
    CursorBasedAdapter,
    IndexInfo,
    SequenceInfo,
    TableInfo,
    TriggerInfo,
)
from sqlit.domains.connections.providers.registry import get_default_port

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


class Db2iAdapter(CursorBasedAdapter):
    """Adapter for IBM DB2 for i using pyodbc with IBM i Access ODBC Driver.
    
    This adapter uses the IBM i Access ODBC Driver which does not require
    an IBM license. The driver must be installed separately on the system.
    """

    @property
    def name(self) -> str:
        return "IBM DB2 for i"

    @property
    def install_extra(self) -> str:
        return "db2i"

    @property
    def install_package(self) -> str:
        return "pyodbc"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("pyodbc",)

    @property
    def supports_multiple_databases(self) -> bool:
        return False

    @property
    def supports_cross_database_queries(self) -> bool:
        return True

    @property
    def supports_stored_procedures(self) -> bool:
        return True

    @property
    def supports_sequences(self) -> bool:
        return True

    @property
    def default_schema(self) -> str:
        return ""

    def connect(self, config: ConnectionConfig) -> Any:
        pyodbc = self._import_driver_module(
            "pyodbc",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        endpoint = config.tcp_endpoint
        if endpoint is None:
            raise ValueError("DB2 for i connections require a TCP-style endpoint.")
        
        # Get optional driver name from config, default to IBM i Access ODBC Driver
        driver_name = config.get_option("odbc_driver", "IBM i Access ODBC Driver")
        
        # Build ODBC connection string
        # Format: DRIVER={driver};SYSTEM=hostname;UID=user;PWD=password;
        conn_str_parts = [
            f"DRIVER={{{driver_name}}}",
            f"SYSTEM={endpoint.host}",
        ]
        
        # Add port if specified (optional for IBM i Access ODBC Driver)
        if endpoint.port:
            conn_str_parts.append(f"PORT={endpoint.port}")
        
        # Add credentials
        if endpoint.username:
            conn_str_parts.append(f"UID={endpoint.username}")
        if endpoint.password:
            conn_str_parts.append(f"PWD={endpoint.password}")
        
        # Add default library (database) if specified
        if endpoint.database:
            conn_str_parts.append(f"DBQ={endpoint.database}")
        
        # Add any extra options from config
        for key, value in config.extra_options.items():
            conn_str_parts.append(f"{key}={value}")
        
        conn_str = ";".join(conn_str_parts) + ";"
        
        conn = pyodbc.connect(conn_str)
        # Enable autocommit for DDL operations
        conn.autocommit = True
        return conn

    def get_databases(self, conn: Any) -> list[str]:
        """Get list of libraries (databases) from DB2 for i."""
        # Libraries are the equivalent of databases in DB2 for i
        # Query QSYS2.SYSTABLES to get distinct schemas/libraries
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT TABLE_SCHEMA FROM QSYS2.SYSTABLES "
            "WHERE TABLE_SCHEMA NOT LIKE 'Q%' "
            "ORDER BY TABLE_SCHEMA"
        )
        return [row[0] for row in cursor.fetchall()]

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        cursor = conn.cursor()
        query = (
            "SELECT TABLE_SCHEMA, TABLE_NAME FROM QSYS2.SYSTABLES "
            "WHERE TABLE_TYPE = 'T' AND TABLE_SCHEMA NOT LIKE 'Q%' "
        )
        if database:
            query += f"AND TABLE_SCHEMA = '{database}' "
        query += "ORDER BY TABLE_SCHEMA, TABLE_NAME"
        
        cursor.execute(query)
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        cursor = conn.cursor()
        query = (
            "SELECT TABLE_SCHEMA, TABLE_NAME FROM QSYS2.SYSVIEWS "
            "WHERE TABLE_SCHEMA NOT LIKE 'Q%' "
        )
        if database:
            query += f"AND TABLE_SCHEMA = '{database}' "
        query += "ORDER BY TABLE_SCHEMA, TABLE_NAME"
        
        cursor.execute(query)
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        cursor = conn.cursor()
        
        # Get primary key columns
        pk_columns: set[str] = set()
        if schema:
            cursor.execute(
                "SELECT COLUMN_NAME FROM QSYS2.SYSCST "
                "WHERE CONSTRAINT_SCHEMA = ? AND CONSTRAINT_NAME IN ("
                "  SELECT CONSTRAINT_NAME FROM QSYS2.SYSCST "
                "  WHERE CONSTRAINT_SCHEMA = ? AND CONSTRAINT_TYPE = 'PRIMARY KEY' "
                "  AND TABLE_SCHEMA = ? AND TABLE_NAME = ?"
                ")",
                (schema, schema, schema, table),
            )
            pk_columns = {row[0] for row in cursor.fetchall()}
        
        # Get column information
        query = (
            "SELECT COLUMN_NAME, DATA_TYPE FROM QSYS2.SYSCOLUMNS "
            "WHERE TABLE_NAME = ? "
        )
        params: list[Any] = [table]
        
        if schema:
            query += "AND TABLE_SCHEMA = ? "
            params.append(schema)
        
        query += "ORDER BY ORDINAL_POSITION"
        
        cursor.execute(query, params)
        return [
            ColumnInfo(name=row[0], data_type=row[1], is_primary_key=row[0] in pk_columns)
            for row in cursor.fetchall()
        ]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        cursor = conn.cursor()
        query = (
            "SELECT ROUTINE_NAME FROM QSYS2.SYSROUTINES "
            "WHERE ROUTINE_SCHEMA NOT LIKE 'Q%' "
            "AND ROUTINE_TYPE = 'PROCEDURE' "
        )
        if database:
            query += f"AND ROUTINE_SCHEMA = '{database}' "
        query += "ORDER BY ROUTINE_NAME"
        
        cursor.execute(query)
        return [row[0] for row in cursor.fetchall()]

    def get_indexes(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[IndexInfo]:
        cursor = conn.cursor()
        query = (
            "SELECT INDEX_NAME, IS_UNIQUE FROM QSYS2.SYSINDEXES "
            "WHERE TABLE_NAME = ? "
        )
        params: list[Any] = [table]
        
        if schema:
            query += "AND TABLE_SCHEMA = ? "
            params.append(schema)
        
        query += "ORDER BY INDEX_NAME"
        
        cursor.execute(query, params)
        return [
            IndexInfo(name=row[0], is_unique=row[1] == 'Y')
            for row in cursor.fetchall()
        ]

    def get_triggers(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[TriggerInfo]:
        cursor = conn.cursor()
        query = (
            "SELECT TRIGGER_NAME, EVENT_MANIPULATION FROM QSYS2.SYSTRIGGERS "
            "WHERE EVENT_OBJECT_TABLE = ? "
        )
        params: list[Any] = [table]
        
        if schema:
            query += "AND TRIGGER_SCHEMA = ? "
            params.append(schema)
        
        query += "ORDER BY TRIGGER_NAME"
        
        cursor.execute(query, params)
        return [
            TriggerInfo(name=row[0], event=row[1])
            for row in cursor.fetchall()
        ]

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        cursor = conn.cursor()
        query = (
            "SELECT SEQUENCE_NAME FROM QSYS2.SYSSEQUENCES "
            "WHERE SEQUENCE_SCHEMA NOT LIKE 'Q%' "
        )
        if database:
            query += f"AND SEQUENCE_SCHEMA = '{database}' "
        query += "ORDER BY SEQUENCE_NAME"
        
        cursor.execute(query)
        return [SequenceInfo(name=row[0]) for row in cursor.fetchall()]

    def get_sequence_info(
        self, conn: Any, sequence_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a DB2 for i sequence."""
        cursor = conn.cursor()
        query = (
            "SELECT START_VALUE, INCREMENT, MIN_VALUE, MAX_VALUE, CYCLE_OPTION "
            "FROM QSYS2.SYSSEQUENCES "
            "WHERE SEQUENCE_NAME = ? "
        )
        params: list[Any] = [sequence_name]
        
        if database:
            query += "AND SEQUENCE_SCHEMA = ? "
            params.append(database)
        
        cursor.execute(query, params)
        row = cursor.fetchone()
        
        if not row:
            return {}
        
        return {
            "start_value": row[0],
            "increment": row[1],
            "min_value": row[2],
            "max_value": row[3],
            "cycle": row[4] == 'YES',
        }

    def quote_identifier(self, name: str) -> str:
        """Quote an identifier for DB2 for i."""
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        """Build SELECT query with FETCH FIRST for DB2 for i."""
        if schema:
            quoted_table = f'{self.quote_identifier(schema)}.{self.quote_identifier(table)}'
        else:
            quoted_table = self.quote_identifier(table)
        return f'SELECT * FROM {quoted_table} FETCH FIRST {limit} ROWS ONLY'

