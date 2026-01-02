"""IBM Db2 adapter using ibm_db_dbi."""

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


class Db2Adapter(CursorBasedAdapter):
    """Adapter for IBM Db2 using ibm_db_dbi."""

    @property
    def name(self) -> str:
        return "IBM Db2"

    @property
    def install_extra(self) -> str:
        return "db2"

    @property
    def install_package(self) -> str:
        return "ibm_db"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("ibm_db_dbi",)

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
        return ""

    def connect(self, config: ConnectionConfig) -> Any:
        ibm_db_dbi = self._import_driver_module(
            "ibm_db_dbi",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        endpoint = config.tcp_endpoint
        if endpoint is None:
            raise ValueError("Db2 connections require a TCP-style endpoint.")
        port = int(endpoint.port or get_default_port("db2"))
        database = endpoint.database
        if not database:
            raise ValueError("Db2 connections require a database name.")

        conn_str = (
            f"DATABASE={database};"
            f"HOSTNAME={endpoint.host};"
            f"PORT={port};"
            "PROTOCOL=TCPIP;"
            f"UID={endpoint.username};"
            f"PWD={endpoint.password};"
        )
        return ibm_db_dbi.connect(conn_str, "", "")

    def get_databases(self, conn: Any) -> list[str]:
        return []

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tabschema, tabname FROM syscat.tables "
            "WHERE type = 'T' AND tabschema NOT LIKE 'SYS%' "
            "ORDER BY tabschema, tabname"
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT viewschema, viewname FROM syscat.views "
            "WHERE viewschema NOT LIKE 'SYS%' "
            "ORDER BY viewschema, viewname"
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        cursor = conn.cursor()
        schema = (schema or "").upper()
        table_name = table.upper()

        pk_columns: set[str] = set()
        if not schema:
            cursor.execute("SELECT CURRENT SCHEMA FROM sysibm.sysdummy1")
            row = cursor.fetchone()
            schema = str(row[0]) if row else ""
        if schema:
            cursor.execute(
                "SELECT k.colname "
                "FROM syscat.tabconst c "
                "JOIN syscat.keycoluse k "
                "  ON c.constname = k.constname "
                " AND c.tabschema = k.tabschema "
                " AND c.tabname = k.tabname "
                "WHERE c.type = 'P' AND c.tabschema = ? AND c.tabname = ?",
                (schema, table_name),
            )
            pk_columns = {row[0] for row in cursor.fetchall()}

        cursor.execute(
            "SELECT colname, typename FROM syscat.columns "
            "WHERE tabschema = ? AND tabname = ? "
            "ORDER BY colno",
            (schema, table_name),
        )
        return [
            ColumnInfo(name=row[0], data_type=row[1], is_primary_key=row[0] in pk_columns)
            for row in cursor.fetchall()
        ]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT procname FROM syscat.procedures "
            "WHERE procschema NOT LIKE 'SYS%' "
            "ORDER BY procname"
        )
        return [row[0] for row in cursor.fetchall()]

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT indname, tabname, uniquerule FROM syscat.indexes "
            "WHERE tabschema NOT LIKE 'SYS%' "
            "ORDER BY tabname, indname"
        )
        return [
            IndexInfo(name=row[0], table_name=row[1], is_unique=row[2] in {"U", "P"})
            for row in cursor.fetchall()
        ]

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT trigname, tabname FROM syscat.triggers "
            "WHERE tabschema NOT LIKE 'SYS%' "
            "ORDER BY tabname, trigname"
        )
        return [TriggerInfo(name=row[0], table_name=row[1]) for row in cursor.fetchall()]

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT seqname FROM syscat.sequences "
            "WHERE seqschema NOT LIKE 'SYS%' "
            "ORDER BY seqname"
        )
        return [SequenceInfo(name=row[0]) for row in cursor.fetchall()]

    def quote_identifier(self, name: str) -> str:
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        schema = schema or ""
        if schema:
            return f'SELECT * FROM "{schema}"."{table}" FETCH FIRST {limit} ROWS ONLY'
        return f'SELECT * FROM "{table}" FETCH FIRST {limit} ROWS ONLY'
