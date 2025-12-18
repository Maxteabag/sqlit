"""Firebird adapter using pyfirebirdsql."""

from typing import TYPE_CHECKING, Any

from .base import ColumnInfo, CursorBasedAdapter, TableInfo

if TYPE_CHECKING:
    from ...config import ConnectionConfig


class FirebirdAdapter(CursorBasedAdapter):
    """Adapter for Firebird using pyfirebirdsql."""

    @property
    def name(self) -> str:
        return "Firebird"

    @property
    def supports_multiple_databases(self) -> bool:
        # Firebird provides no mechanism to list databases or aliases.
        return False

    @property
    def supports_stored_procedures(self) -> bool:
        return True

    def connect(self, config: "ConnectionConfig") -> Any:
        """Connect to a Firebird database."""
        import firebirdsql

        conn = firebirdsql.connect(
            host=config.server or "localhost",
            port=int(config.port) if config.port else 3050,
            database=config.database or "security.db",
            user=config.username,
            password=config.password,
        )
        return conn

    def get_databases(self, conn: Any) -> list[str]:
        # Firebird provides no mechanism to list databases or aliases.
        return []

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """List the tables in the database associated with the connection."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT rdb$relation_name "
            "FROM   rdb$relations "
            "WHERE  rdb$view_blr IS NULL AND (rdb$system_flag IS NULL OR rdb$system_flag = 0)"
        )
        return [("", row[0]) for row in cursor.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """List the views in the database associated with the connection."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT rdb$relation_name "
            "FROM   rdb$relations "
            "WHERE  rdb$view_blr IS NOT NULL AND (rdb$system_flag IS NULL OR rdb$system_flag = 0)"
        )
        return [("", row[0].rstrip()) for row in cursor.fetchall()]

    # Map type IDs to type names
    _types = {
        7: "SMALLINT",
        8: "INTEGER",
        10: "FLOAT",
        12: "DATE",
        13: "TIME",
        14: "CHAR",
        16: "BIGINT",
        27: "DOUBLE PRECISION",
        35: "TIMESTAMP",
        37: "VARCHAR",
        261: "BLOB",
    }

    def get_columns(
        self,
        conn: Any,
        table: str,
        database: str | None = None,
        schema: str | None = None,
    ) -> list[ColumnInfo]:
        """List the fields of a given table and their types."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT rf.rdb$field_name, f.rdb$field_type, f.rdb$character_length "
            "FROM   rdb$relation_fields AS rf "
            "JOIN   rdb$fields AS f ON f.rdb$field_name = rf.rdb$field_source "
            "WHERE  rdb$relation_name = ? "
            "ORDER BY rdb$field_position ASC",
            (table,),
        )
        columns = []
        for row in cursor.fetchall():
            if row[1] in [14, 37]:  # CHAR, VARCHAR
                data_type = f"{self._types[row[1]]}({row[2]})"
            else:
                data_type = self._types[row[1]]
            columns.append(ColumnInfo(name=row[0].rstrip(), data_type=data_type))
        return columns

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """List any stored procedures in the database."""
        cursor = conn.cursor()
        cursor.execute("SELECT rdb$procedure_name FROM rdb$procedures")
        return [row[0] for row in cursor.fetchall()]

    def quote_identifier(self, name: str) -> str:
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def build_select_query(
        self,
        table: str,
        limit: int,
        database: str | None = None,
        schema: str | None = None,
    ) -> str:
        """Build SELECT LIMIT query."""
        return f'SELECT * FROM "{table}" ROWS {limit}'
