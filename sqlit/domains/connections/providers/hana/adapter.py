"""SAP HANA adapter using hdbcli."""

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


class HanaAdapter(CursorBasedAdapter):
    """Adapter for SAP HANA using hdbcli."""

    @property
    def name(self) -> str:
        return "SAP HANA"

    @property
    def install_extra(self) -> str:
        return "hana"

    @property
    def install_package(self) -> str:
        return "hdbcli"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("hdbcli",)

    @property
    def supports_multiple_databases(self) -> bool:
        return False

    @property
    def supports_cross_database_queries(self) -> bool:
        return False

    @property
    def supports_stored_procedures(self) -> bool:
        return True

    @property
    def supports_sequences(self) -> bool:
        return True

    @property
    def default_schema(self) -> str:
        return "PUBLIC"

    def connect(self, config: ConnectionConfig) -> Any:
        hdbcli = self._import_driver_module(
            "hdbcli.dbapi",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        endpoint = config.tcp_endpoint
        if endpoint is None:
            raise ValueError("SAP HANA connections require a TCP-style endpoint.")
        port = int(endpoint.port or get_default_port("hana"))
        connect_args: dict[str, Any] = {
            "address": endpoint.host,
            "port": port,
            "user": endpoint.username,
            "password": endpoint.password,
        }
        if endpoint.database:
            connect_args["databaseName"] = endpoint.database

        schema = config.get_option("schema")
        if schema:
            connect_args["currentSchema"] = schema

        return hdbcli.connect(**connect_args)

    def get_databases(self, conn: Any) -> list[str]:
        return []

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT schema_name, table_name FROM sys.tables "
            "WHERE schema_name NOT LIKE '_SYS%' "
            "AND schema_name NOT IN ('SYS', 'SYSTEM') "
            "ORDER BY schema_name, table_name"
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT schema_name, view_name FROM sys.views "
            "WHERE schema_name NOT LIKE '_SYS%' "
            "AND schema_name NOT IN ('SYS', 'SYSTEM') "
            "ORDER BY schema_name, view_name"
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        cursor = conn.cursor()
        schema = schema or self.default_schema

        cursor.execute(
            "SELECT cc.column_name "
            "FROM sys.constraints c "
            "JOIN sys.constraint_columns cc "
            "  ON c.schema_name = cc.schema_name "
            " AND c.constraint_name = cc.constraint_name "
            "WHERE c.constraint_type = 'PRIMARY KEY' "
            "AND c.schema_name = ? AND c.table_name = ?",
            (schema, table),
        )
        pk_columns = {row[0] for row in cursor.fetchall()}

        cursor.execute(
            "SELECT column_name, data_type_name FROM sys.columns "
            "WHERE schema_name = ? AND table_name = ? "
            "ORDER BY position",
            (schema, table),
        )
        return [
            ColumnInfo(name=row[0], data_type=row[1], is_primary_key=row[0] in pk_columns)
            for row in cursor.fetchall()
        ]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT procedure_name FROM sys.procedures "
            "WHERE schema_name NOT LIKE '_SYS%' "
            "AND schema_name NOT IN ('SYS', 'SYSTEM') "
            "ORDER BY procedure_name"
        )
        return [row[0] for row in cursor.fetchall()]

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT index_name, table_name, is_unique FROM sys.indexes "
            "WHERE schema_name NOT LIKE '_SYS%' "
            "AND schema_name NOT IN ('SYS', 'SYSTEM') "
            "ORDER BY table_name, index_name"
        )
        return [
            IndexInfo(name=row[0], table_name=row[1], is_unique=bool(row[2]))
            for row in cursor.fetchall()
        ]

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT trigger_name, subject_table_name FROM sys.triggers "
            "WHERE schema_name NOT LIKE '_SYS%' "
            "AND schema_name NOT IN ('SYS', 'SYSTEM') "
            "ORDER BY subject_table_name, trigger_name"
        )
        return [TriggerInfo(name=row[0], table_name=row[1]) for row in cursor.fetchall()]

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT sequence_name FROM sys.sequences "
            "WHERE schema_name NOT LIKE '_SYS%' "
            "AND schema_name NOT IN ('SYS', 'SYSTEM') "
            "ORDER BY sequence_name"
        )
        return [SequenceInfo(name=row[0]) for row in cursor.fetchall()]

    def quote_identifier(self, name: str) -> str:
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        schema = schema or self.default_schema
        return f'SELECT * FROM "{schema}"."{table}" LIMIT {limit}'
