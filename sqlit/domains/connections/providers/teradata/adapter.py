"""Teradata adapter using teradatasql."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.adapters.base import (
    ColumnInfo,
    CursorBasedAdapter,
    IndexInfo,
    TableInfo,
    TriggerInfo,
)
from sqlit.domains.connections.providers.registry import get_default_port

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


class TeradataAdapter(CursorBasedAdapter):
    """Adapter for Teradata using teradatasql."""

    @property
    def name(self) -> str:
        return "Teradata"

    @property
    def install_extra(self) -> str:
        return "teradata"

    @property
    def install_package(self) -> str:
        return "teradatasql"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("teradatasql",)

    @property
    def supports_multiple_databases(self) -> bool:
        return True

    @property
    def supports_cross_database_queries(self) -> bool:
        return True

    @property
    def supports_stored_procedures(self) -> bool:
        return True

    def apply_database_override(self, config: ConnectionConfig, database: str) -> ConnectionConfig:
        """Apply a default database for unqualified queries."""
        if not database:
            return config
        return config.with_endpoint(database=database)

    @property
    def system_databases(self) -> frozenset[str]:
        return frozenset({"dbc", "syslib", "sysudtlib", "sysuif", "sysbar", "sysadmin"})

    def connect(self, config: ConnectionConfig) -> Any:
        teradatasql = self._import_driver_module(
            "teradatasql",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        endpoint = config.tcp_endpoint
        if endpoint is None:
            raise ValueError("Teradata connections require a TCP-style endpoint.")
        port = int(endpoint.port or get_default_port("teradata"))
        connect_args: dict[str, Any] = {
            "host": endpoint.host,
            "user": endpoint.username,
            "password": endpoint.password,
        }
        if endpoint.database:
            connect_args["database"] = endpoint.database
        if port:
            connect_args["dbs_port"] = port

        connect_args.update(config.extra_options)
        return teradatasql.connect(**connect_args)

    def get_databases(self, conn: Any) -> list[str]:
        cursor = conn.cursor()
        cursor.execute(
            "lock row for access "
            "SELECT DatabaseName FROM DBC.DatabasesV "
            "WHERE dbkind IN ('D', 'U') "
            "ORDER BY DatabaseName"
        )
        return [row[0] for row in cursor.fetchall()]

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "lock row for access "
                "SELECT DatabaseName, TableName FROM DBC.TablesV "
                "WHERE TableKind = 'T' AND DatabaseName = ? "
                "ORDER BY TableName",
                (database,),
            )
        else:
            cursor.execute(
                "lock row for access "
                "SELECT DatabaseName, TableName FROM DBC.TablesV "
                "WHERE TableKind = 'T' "
                "ORDER BY DatabaseName, TableName"
            )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "lock row for access "
                "SELECT DatabaseName, TableName FROM DBC.TablesV "
                "WHERE TableKind = 'V' AND DatabaseName = ? "
                "ORDER BY TableName",
                (database,),
            )
        else:
            cursor.execute(
                "lock row for access "
                "SELECT DatabaseName, TableName FROM DBC.TablesV "
                "WHERE TableKind = 'V' "
                "ORDER BY DatabaseName, TableName"
            )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        cursor = conn.cursor()
        schema_name = schema or database
        if not schema_name:
            return []

        pk_columns: set[str] = set()
        try:
            cursor.execute(
                "lock row for access "
                "select "
                    "COLUMNNAME "
                "from DBC.INDICESV "
                "where DATABASENAME = ? "
                  "and TABLENAME    = ? "
                  "and INDEXTYPE = 'P' ",
                (schema_name, table),
            )
            pk_columns = {row[0] for row in cursor.fetchall()}
        except Exception:
            pk_columns = set()

        cursor.execute(
                "lock row for access "
            "SELECT ColumnName, ColumnType FROM DBC.ColumnsV "
            "WHERE DatabaseName = ? AND TableName = ? "
            "ORDER BY ColumnId",
            (schema_name, table),
        )
        return [
            ColumnInfo(name=row[0], data_type=row[1], is_primary_key=row[0] in pk_columns)
            for row in cursor.fetchall()
        ]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "lock row for access "
                "SELECT TableName FROM DBC.TablesV "
                "WHERE TableKind = 'P' AND DatabaseName = ? "
                "ORDER BY TableName",
                (database,),
            )
        else:
            cursor.execute(
                "lock row for access "
                "SELECT TableName FROM DBC.TablesV "
                "WHERE TableKind = 'P' "
                "ORDER BY TableName"
            )
        return [row[0] for row in cursor.fetchall()]

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "lock row for access "
                "SELECT IndexName, TableName, UniqueFlag FROM DBC.IndicesV "
                "WHERE DatabaseName = ? "
                "ORDER BY TableName, IndexName",
                (database,),
            )
        else:
            cursor.execute(
                "lock row for access "
                "SELECT IndexName, TableName, UniqueFlag FROM DBC.IndicesV "
                "ORDER BY DatabaseName, TableName, IndexName"
            )
        return [
            IndexInfo(name=row[0], table_name=row[1], is_unique=str(row[2]).upper() == "Y")
            for row in cursor.fetchall()
        ]

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "lock row for access "
                "SELECT TriggerName, TableName FROM DBC.TriggersV "
                "WHERE DatabaseName = ? "
                "ORDER BY TableName, TriggerName",
                (database,),
            )
        else:
            cursor.execute(
                "lock row for access "
                "SELECT TriggerName, TableName FROM DBC.TriggersV "
                "ORDER BY DatabaseName, TableName, TriggerName"
            )
        return [TriggerInfo(name=row[0], table_name=row[1]) for row in cursor.fetchall()]

    def get_sequences(self, conn: Any, database: str | None = None) -> list[str]:
        """Teradata does not support standalone sequences.

        Auto-increment behaviour is provided by IDENTITY columns instead.
        """
        return []

    def quote_identifier(self, name: str) -> str:
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        schema_name = schema or database
        if schema_name:
            return f'lock row for access select top {limit} * from "{schema_name}"."{table}"'
        return f'lock row for access select top {limit} * from "{table}"'
