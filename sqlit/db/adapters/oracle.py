"""Oracle Database adapter using oracledb."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..schema import get_default_port
from .base import ColumnInfo, DatabaseAdapter, IndexInfo, SequenceInfo, TableInfo, TriggerInfo

if TYPE_CHECKING:
    from ...config import ConnectionConfig


class OracleAdapter(DatabaseAdapter):
    """Adapter for Oracle Database using oracledb.

    Note: Oracle uses schemas extensively, but user_tables/user_views return
    only objects owned by the current user (which acts as the default schema).
    """

    @property
    def name(self) -> str:
        return "Oracle"

    @property
    def install_extra(self) -> str:
        return "oracle"

    @property
    def install_package(self) -> str:
        return "oracledb"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("oracledb",)

    @property
    def supports_multiple_databases(self) -> bool:
        # Oracle uses schemas within a single database, not multiple databases
        return False

    @property
    def supports_stored_procedures(self) -> bool:
        return True

    @property
    def supports_sequences(self) -> bool:
        """Oracle supports sequences."""
        return True

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to Oracle database."""
        try:
            import oracledb
        except ImportError as e:
            from ...db.exceptions import MissingDriverError

            if not self.install_extra or not self.install_package:
                raise e
            raise MissingDriverError(self.name, self.install_extra, self.install_package) from e

        port = int(config.port or get_default_port("oracle"))
        # Use Easy Connect string format: host:port/service_name
        dsn = f"{config.server}:{port}/{config.database}"

        # Determine connection mode based on oracle_role
        oracle_role = getattr(config, "oracle_role", "normal")
        mode = None
        if oracle_role == "sysdba":
            mode = oracledb.AUTH_MODE_SYSDBA
        elif oracle_role == "sysoper":
            mode = oracledb.AUTH_MODE_SYSOPER

        connect_kwargs: dict[str, Any] = {
            "user": config.username,
            "password": config.password,
            "dsn": dsn,
        }
        if mode is not None:
            connect_kwargs["mode"] = mode

        return oracledb.connect(**connect_kwargs)

    def get_databases(self, conn: Any) -> list[str]:
        """Oracle doesn't support multiple databases - return empty list."""
        return []

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables from Oracle. Returns (schema, name) with empty schema."""
        cursor = conn.cursor()
        cursor.execute("SELECT table_name FROM user_tables ORDER BY table_name")
        # user_tables returns only current user's tables, so no schema prefix needed
        return [("", row[0]) for row in cursor.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of views from Oracle. Returns (schema, name) with empty schema."""
        cursor = conn.cursor()
        cursor.execute("SELECT view_name FROM user_views ORDER BY view_name")
        return [("", row[0]) for row in cursor.fetchall()]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get columns for a table from Oracle. Schema parameter is ignored."""
        cursor = conn.cursor()

        # Get primary key columns
        cursor.execute(
            "SELECT cols.column_name "
            "FROM user_constraints cons "
            "JOIN user_cons_columns cols ON cons.constraint_name = cols.constraint_name "
            "WHERE cons.constraint_type = 'P' AND cons.table_name = :1",
            (table.upper(),),
        )
        pk_columns = {row[0] for row in cursor.fetchall()}

        # Get all columns
        cursor.execute(
            "SELECT column_name, data_type FROM user_tab_columns " "WHERE table_name = :1 ORDER BY column_id",
            (table.upper(),),
        )
        return [ColumnInfo(name=row[0], data_type=row[1], is_primary_key=row[0] in pk_columns) for row in cursor.fetchall()]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """Get stored procedures from Oracle."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT object_name FROM user_procedures " "WHERE object_type = 'PROCEDURE' ORDER BY object_name"
        )
        return [row[0] for row in cursor.fetchall()]

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        """Get indexes from Oracle."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT index_name, table_name, uniqueness "
            "FROM user_indexes "
            "WHERE index_type != 'LOB' "
            "ORDER BY table_name, index_name"
        )
        return [
            IndexInfo(name=row[0], table_name=row[1], is_unique=row[2] == "UNIQUE")
            for row in cursor.fetchall()
        ]

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        """Get triggers from Oracle."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT trigger_name, table_name "
            "FROM user_triggers "
            "WHERE base_object_type = 'TABLE' "
            "ORDER BY table_name, trigger_name"
        )
        return [TriggerInfo(name=row[0], table_name=row[1] or "") for row in cursor.fetchall()]

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        """Get sequences from Oracle."""
        cursor = conn.cursor()
        cursor.execute("SELECT sequence_name FROM user_sequences ORDER BY sequence_name")
        return [SequenceInfo(name=row[0]) for row in cursor.fetchall()]

    def get_index_definition(
        self, conn: Any, index_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about an Oracle index."""
        cursor = conn.cursor()
        # Get index info
        cursor.execute(
            "SELECT uniqueness, index_type FROM user_indexes WHERE index_name = :1",
            (index_name.upper(),),
        )
        row = cursor.fetchone()
        is_unique = row[0] == "UNIQUE" if row else False
        index_type = row[1] if row else "NORMAL"

        # Get index columns
        cursor.execute(
            "SELECT column_name FROM user_ind_columns "
            "WHERE index_name = :1 ORDER BY column_position",
            (index_name.upper(),),
        )
        columns = [row[0] for row in cursor.fetchall()]

        # Try to get DDL
        try:
            cursor.execute(
                "SELECT DBMS_METADATA.GET_DDL('INDEX', :1) FROM dual",
                (index_name.upper(),),
            )
            ddl_row = cursor.fetchone()
            definition = str(ddl_row[0]) if ddl_row else None
        except Exception:
            definition = f"CREATE {'UNIQUE ' if is_unique else ''}INDEX {index_name} ON {table_name} ({', '.join(columns)})"

        return {
            "name": index_name,
            "table_name": table_name,
            "columns": columns,
            "is_unique": is_unique,
            "type": index_type,
            "definition": definition,
        }

    def get_trigger_definition(
        self, conn: Any, trigger_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about an Oracle trigger."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT trigger_type, triggering_event, trigger_body "
            "FROM user_triggers WHERE trigger_name = :1",
            (trigger_name.upper(),),
        )
        row = cursor.fetchone()
        if row:
            # trigger_type is like "BEFORE EACH ROW" or "AFTER STATEMENT"
            timing = row[0].split()[0] if row[0] else None
            return {
                "name": trigger_name,
                "table_name": table_name,
                "timing": timing,
                "event": row[1],
                "definition": row[2],
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
        """Get detailed information about an Oracle sequence."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT min_value, max_value, increment_by, cycle_flag, last_number "
            "FROM user_sequences WHERE sequence_name = :1",
            (sequence_name.upper(),),
        )
        row = cursor.fetchone()
        if row:
            return {
                "name": sequence_name,
                "start_value": row[4],  # last_number approximates current position
                "increment": row[2],
                "min_value": row[0],
                "max_value": row[1],
                "cycle": row[3] == "Y",
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
        """Quote identifier using double quotes for Oracle.

        Escapes embedded double quotes by doubling them.
        """
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        """Build SELECT query with FETCH FIRST for Oracle 12c+. Schema parameter is ignored."""
        return f'SELECT * FROM "{table}" FETCH FIRST {limit} ROWS ONLY'

    def execute_query(self, conn: Any, query: str, max_rows: int | None = None) -> tuple[list[str], list[tuple], bool]:
        """Execute a query on Oracle with optional row limit."""
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
        """Execute a non-query on Oracle."""
        cursor = conn.cursor()
        cursor.execute(query)
        rowcount = int(cursor.rowcount)
        conn.commit()
        return rowcount
