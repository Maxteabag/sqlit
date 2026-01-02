"""Firebird adapter using pyfirebirdsql."""

from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.adapters.base import (
    ColumnInfo,
    CursorBasedAdapter,
    IndexInfo,
    SequenceInfo,
    TableInfo,
    TriggerInfo,
)

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


class FirebirdAdapter(CursorBasedAdapter):
    """Adapter for Firebird using pyfirebirdsql."""

    @property
    def name(self) -> str:
        return "Firebird"

    @property
    def install_extra(self) -> str | None:
        return "firebird"

    @property
    def install_package(self) -> str | None:
        return "firebirdsql"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("firebirdsql",)

    @property
    def supports_multiple_databases(self) -> bool:
        # Firebird provides no mechanism to list databases or aliases.
        return False

    @property
    def supports_stored_procedures(self) -> bool:
        return True

    @property
    def supports_indexes(self) -> bool:
        return True

    @property
    def supports_sequences(self) -> bool:
        # NOTE: Firebird refers to sequences as 'generators'
        return True

    @property
    def supports_triggers(self) -> bool:
        return True

    @property
    def test_query(self) -> str:
        return "SELECT 1 FROM rdb$database"

    def connect(self, config: "ConnectionConfig") -> Any:
        """Connect to a Firebird database."""
        firebirdsql = self._import_driver_module(
            "firebirdsql",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        endpoint = config.tcp_endpoint
        if endpoint is None:
            raise ValueError("Firebird connections require a TCP-style endpoint.")
        conn = firebirdsql.connect(
            host=endpoint.host or "localhost",
            port=int(endpoint.port) if endpoint.port else 3050,
            database=endpoint.database or "security.db",
            user=endpoint.username,
            password=endpoint.password,
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

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT rdb$index_name, rdb$relation_name, rdb$unique_flag FROM rdb$indices WHERE rdb$system_flag = 0"
        )
        return [
            IndexInfo(
                name=row[0].rstrip(),
                table_name=row[1].rstrip(),
                is_unique=row[2] == 1,
            )
            for row in cursor.fetchall()
        ]

    def get_index_definition(
        self,
        conn: Any,
        index_name: str,
        table_name: str,
        database: str | None = None,
    ) -> dict[str, Any]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT rdb$unique_flag, rdb$index_type, rdb$segment_count, rdb$expression_source "
            "FROM   rdb$indices "
            "WHERE  rdb$index_name = ? AND rdb$system_flag = 0",
            (index_name.upper(),),
        )
        meta = cursor.fetchone()
        is_unique = meta[0] == 1
        descending = meta[1] == 1

        if meta[2] > 0:
            cursor.execute(
                "SELECT rdb$field_name FROM rdb$index_segments WHERE rdb$index_name = ? ORDER BY rdb$field_position",
                (index_name.upper(),),
            )
            columns = [row[0] for row in cursor.fetchall()]
        else:
            columns = []

        definition_parts = ["CREATE"]
        definition_parts.append("DESCENDING" if descending else "ASCENDING")
        if is_unique:
            definition_parts.append("UNIQUE")
        definition_parts += ["INDEX", index_name.upper(), "ON", table_name.upper()]
        if columns:
            definition_parts.append(f"({', '.join(columns)})")
        else:
            definition_parts.append(f"COMPUTED BY ({meta[3]})")

        return {
            "name": index_name.upper(),
            "table_name": table_name.upper(),
            "columns": columns,
            "is_unique": is_unique,
            "definition": " ".join(definition_parts),
        }

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        cursor = conn.cursor()
        cursor.execute("SELECT rdb$generator_name FROM rdb$generators WHERE rdb$system_flag = 0")
        return [SequenceInfo(name=row[0].rstrip()) for row in cursor.fetchall()]

    def get_sequence_definition(
        self,
        conn: Any,
        sequence_name: str,
        database: str | None = None,
    ) -> dict[str, Any]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT  rdb$initial_value, rdb$generator_increment "
            "FROM    rdb$generators "
            "WHERE   rdb$system_flag = 0 AND rdb$generator_name = ?",
            (sequence_name.upper(),),
        )
        row = cursor.fetchone()
        if row:
            return {
                "name": sequence_name.upper(),
                "start_value": row[0],
                "increment": row[1],
                "min_value": None,
                "max_value": None,
                "cycle": None,
            }
        return {
            "name": sequence_name.upper(),
            "start_value": None,
            "increment": None,
            "min_value": None,
            "max_value": None,
            "cycle": None,
        }

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        cursor = conn.cursor()
        cursor.execute("SELECT rdb$trigger_name, rdb$relation_name FROM rdb$triggers WHERE rdb$system_flag = 0")
        return [TriggerInfo(name=row[0].rstrip(), table_name=row[1].rstrip()) for row in cursor.fetchall()]

    _trigger_types = {
        1: "BEFORE INSERT",
        2: "AFTER INSERT",
        3: "BEFORE UPDATE",
        4: "AFTER UPDATE",
        5: "BEFORE DELETE",
        6: "AFTER DELETE",
        17: "BEFORE INSERT OR UPDATE",
        18: "AFTER INSERT OR UPDATE",
        25: "BEFORE INSERT OR DELETE",
        26: "AFTER INSERT OR DELETE",
        27: "BEFORE UPDATE OR DELETE",
        28: "AFTER UPDATE OR DELETE",
        113: "BEFORE INSERT OR UPDATE OR DELETE",
        114: "AFTER INSERT OR UPDATE OR DELETE",
        8192: "ON CONNECT",
        8193: "ON DISCONNECT",
        8194: "ON TRANSACTION START",
        8195: "ON TRANSACTION COMMIT",
        8196: "ON TRANSACTION ROLLBACK",
    }

    def get_trigger_definition(
        self,
        conn: Any,
        trigger_name: str,
        table_name: str,
        database: str | None = None,
    ) -> dict[str, Any]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT rdb$trigger_type, rdb$trigger_source FROM rdb$triggers WHERE rdb$trigger_name = ?",
            (trigger_name.upper(),),
        )
        row = cursor.fetchone()
        if row:
            event = self._trigger_types[row[0]]
            if event.startswith(("BEFORE ", "AFTER")):
                timing, event = event.split(" ", maxsplit=1)
            else:
                timing = None
            return {
                "name": trigger_name.upper(),
                "table_name": table_name.upper(),
                "timing": timing,
                "event": event,
                "definition": row[1],
            }
        return {
            "name": trigger_name.upper(),
            "table_name": table_name.upper(),
            "timing": None,
            "event": None,
            "definition": None,
        }

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

        # Find the fields that form part of the primary key
        cursor.execute(
            "SELECT    sg.rdb$field_name "
            "FROM      rdb$indices AS ix "
            "JOIN      rdb$index_segments AS sg USING (rdb$index_name) "
            "LEFT JOIN rdb$relation_constraints AS rc USING (rdb$index_name) "
            "WHERE     rc.rdb$constraint_type = 'PRIMARY KEY' AND rc.rdb$relation_name = ?",
            (table.upper(),),
        )
        pk_fields = set(row[0].rstrip() for row in cursor.fetchall())

        # Find the fields themselves.
        cursor.execute(
            "SELECT rf.rdb$field_name, f.rdb$field_type, f.rdb$character_length "
            "FROM   rdb$relation_fields AS rf "
            "JOIN   rdb$fields AS f ON f.rdb$field_name = rf.rdb$field_source "
            "WHERE  rdb$relation_name = ? "
            "ORDER BY rdb$field_position ASC",
            (table.upper(),),
        )
        columns = []
        for row in cursor.fetchall():
            if row[1] in [14, 37]:  # CHAR, VARCHAR
                data_type = f"{self._types[row[1]]}({row[2]})"
            else:
                data_type = self._types[row[1]]
            name = row[0].rstrip()
            columns.append(ColumnInfo(name=name, data_type=data_type, is_primary_key=name in pk_fields))
        return columns

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """List any stored procedures in the database."""
        cursor = conn.cursor()
        cursor.execute("SELECT rdb$procedure_name FROM rdb$procedures WHERE rdb$system_flag = 0")
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

    def execute_non_query(self, conn: Any, query: str) -> int:
        # Firebird has no autocommit mode, so we need to guarantee it ourselves.
        try:
            return super().execute_non_query(conn, query)
        finally:
            conn.commit()
