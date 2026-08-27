"""Oracle Database adapter using oracledb."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.adapters.base import (
    ColumnInfo,
    DatabaseAdapter,
    ForeignKeyInfo,
    IndexInfo,
    SequenceInfo,
    TableInfo,
    TriggerInfo,
)
from sqlit.domains.connections.providers.registry import get_default_port

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


_LEADING_SQL_COMMENTS = re.compile(
    r"^\s*(?:(?:--[^\n]*(?:\n|$))|(?:/\*.*?\*/\s*))*",
    re.DOTALL,
)
_PLSQL_START = re.compile(
    r"^(?:BEGIN|DECLARE)\b|^CREATE\s+(?:OR\s+REPLACE\s+)?"
    r"(?:(?:NON)?EDITIONABLE\s+)?"
    r"(?:FUNCTION|PACKAGE|PROCEDURE|TRIGGER|TYPE\s+BODY)\b",
    re.IGNORECASE,
)


def _dictionary_qualified_name(owner: str, name: str) -> str:
    """Keep the owner/object boundary recoverable for quoted dotted names."""
    if any(char in owner + name for char in '."'):

        def quote(value: str) -> str:
            return '"' + value.replace('"', '""') + '"'

        return f"{quote(owner)}.{quote(name)}"
    return f"{owner}.{name}"


def _split_dictionary_name(value: str) -> tuple[str | None, str]:
    """Decode names emitted by `_dictionary_qualified_name`."""
    if value.startswith('"'):
        match = re.fullmatch(r'"((?:""|[^"])*)"\."((?:""|[^"])*)"', value)
        if match:
            return match.group(1).replace('""', '"'), match.group(2).replace('""', '"')
    if "." in value:
        owner, name = value.split(".", 1)
        return owner, name
    return None, value.upper()


def _prepare_statement(query: str) -> str:
    """Remove SQL*Plus terminators that python-oracledb does not accept."""
    statement = query.rstrip()
    if not statement.endswith(";"):
        return query

    without_leading_comments = _LEADING_SQL_COMMENTS.sub("", statement)
    if _PLSQL_START.match(without_leading_comments):
        return query

    return statement[:-1].rstrip()


class OracleAdapter(DatabaseAdapter):
    """Adapter for Oracle Database using oracledb.

    Oracle schemas are users.  The ALL_* dictionary views expose objects the
    connected user may access, including objects owned by other schemas.
    """

    _client_mode_default = "thin"

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

    @property
    def supports_foreign_keys(self) -> bool:
        return True

    @property
    def test_query(self) -> str:
        return "SELECT 1 FROM DUAL"

    def _ensure_client_mode(self, oracledb: Any, config: ConnectionConfig) -> None:
        """Enable Thick mode before the first connection when requested.

        python-oracledb chooses one mode for the lifetime of the process, so
        initialization must happen before ``connect()``. Calling
        ``init_oracle_client()`` repeatedly with the same arguments is
        supported by the driver.
        """
        client_mode = str(
            config.get_option("oracle_client_mode", self._client_mode_default)
        ).strip().lower()
        if client_mode == "thin":
            is_thin_mode = getattr(oracledb, "is_thin_mode", None)
            if callable(is_thin_mode) and is_thin_mode() is False:
                raise ValueError(
                    "Oracle Thin mode cannot be selected after Thick mode was "
                    "initialized in this sqlit process. Restart sqlit before "
                    "opening this connection."
                )
            return
        if client_mode != "thick":
            raise ValueError("Oracle client mode must be Thin or Thick")

        lib_dir = str(
            config.get_option("oracle_client_lib_dir", "") or ""
        ).strip()
        try:
            if lib_dir:
                oracledb.init_oracle_client(lib_dir=lib_dir)
            else:
                oracledb.init_oracle_client()
        except Exception as exc:
            raise ValueError(
                "Oracle Thick mode initialization failed. Install Oracle Client "
                "libraries and make them available to sqlit before connecting. "
                "Restart sqlit if a Thin-mode connection was already opened. "
                f"Driver error: {exc}"
            ) from exc

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to Oracle database."""
        oracledb = self._import_driver_module(
            "oracledb",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        self._ensure_client_mode(oracledb, config)

        # Fetch CLOB/BLOB values inline as str/bytes instead of LOB locators.
        # Locators need a live connection to be read, but results are pickled
        # across the process worker pipe after the query connection is closed,
        # which raises DPY-1001 mid-serialization. Inline fetch also avoids
        # one extra round trip per LOB per row.
        oracledb.defaults.fetch_lobs = False

        endpoint = config.tcp_endpoint
        if endpoint is None:
            raise ValueError("Oracle connections require a TCP-style endpoint.")
        port = int(endpoint.port or get_default_port("oracle"))

        # Determine connection type: service_name (default) or sid
        connection_type = config.get_option("oracle_connection_type", "service_name")

        if connection_type == "sid":
            # Thin-mode Easy Connect doesn't accept the legacy host:port:SID form;
            # it tries to resolve the string as a TNS alias and fails with DPY-4027.
            # makedsn emits a full TNS descriptor that thin mode handles directly.
            sid = config.get_option("oracle_sid") or endpoint.database
            dsn = oracledb.makedsn(endpoint.host, port, sid=sid)
        else:
            protocol = str(config.get_option("oracle_protocol", "default")).strip().lower()
            if protocol not in {"", "default", "tcp", "tcps"}:
                raise ValueError("Oracle protocol must be Default, TCP, or TCPS")
            protocol_prefix = f"{protocol}://" if protocol in {"tcp", "tcps"} else ""
            dsn = f"{protocol_prefix}{endpoint.host}:{port}/{endpoint.database}"

            parameters = str(config.get_option("oracle_easy_connect_parameters", "") or "").strip()
            parameters = parameters.lstrip("?")
            if parameters:
                dsn = f"{dsn}?{parameters}"

        # Determine connection mode based on oracle_role
        oracle_role = config.get_option("oracle_role", "normal")
        mode = None
        if oracle_role == "sysdba":
            mode = oracledb.AUTH_MODE_SYSDBA
        elif oracle_role == "sysoper":
            mode = oracledb.AUTH_MODE_SYSOPER

        connect_kwargs: dict[str, Any] = {
            "user": endpoint.username,
            "password": endpoint.password,
            "dsn": dsn,
        }
        if mode is not None:
            connect_kwargs["mode"] = mode

        connect_kwargs.update(config.extra_options)
        return oracledb.connect(**connect_kwargs)

    def get_databases(self, conn: Any) -> list[str]:
        """Oracle doesn't support multiple databases - return empty list."""
        return []

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get all tables accessible to the connected Oracle user."""
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT owner, table_name FROM all_tables ORDER BY owner, table_name")
            return [(row[0], row[1]) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get all views accessible to the connected Oracle user."""
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT owner, view_name FROM all_views ORDER BY owner, view_name")
            return [(row[0], row[1]) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def get_columns(self, conn: Any, table: str, database: str | None = None, schema: str | None = None) -> list[ColumnInfo]:
        """Get columns for a table from Oracle, scoped to its owning schema."""
        if schema:
            constraints_view = "all_constraints"
            constraint_columns_view = "all_cons_columns"
            columns_view = "all_tab_columns"
            owner_clause = " AND cons.owner = :owner_name AND cols.owner = :owner_name"
            columns_owner_clause = " AND owner = :owner_name"
            params = {"table_name": table, "owner_name": schema}
        else:
            constraints_view = "user_constraints"
            constraint_columns_view = "user_cons_columns"
            columns_view = "user_tab_columns"
            owner_clause = ""
            columns_owner_clause = ""
            params = {"table_name": table.upper()}

        # Get primary key columns
        pk_cursor = conn.cursor()
        try:
            pk_cursor.execute(
                "SELECT cols.column_name "
                f"FROM {constraints_view} cons "
                f"JOIN {constraint_columns_view} cols "
                "ON cons.constraint_name = cols.constraint_name "
                "AND cons.owner = cols.owner "
                "WHERE cons.constraint_type = 'P' AND cons.table_name = :table_name"
                f"{owner_clause}",
                params,
            )
            pk_columns = {row[0] for row in pk_cursor.fetchall()}
        finally:
            pk_cursor.close()

        # Get all columns
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"SELECT column_name, data_type FROM {columns_view} WHERE table_name = :table_name{columns_owner_clause} ORDER BY column_id",
                params,
            )
            return [ColumnInfo(name=row[0], data_type=row[1], is_primary_key=row[0] in pk_columns) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """Get stored procedures from Oracle."""
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT owner, object_name FROM all_procedures WHERE object_type = 'PROCEDURE' ORDER BY owner, object_name")
            return [_dictionary_qualified_name(row[0], row[1]) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        """Get indexes from Oracle."""
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT owner, index_name, table_owner, table_name, uniqueness FROM all_indexes WHERE index_type != 'LOB' ORDER BY owner, table_owner, table_name, index_name")
            return [IndexInfo(name=_dictionary_qualified_name(row[0], row[1]), table_name=_dictionary_qualified_name(row[2], row[3]), is_unique=row[4] == "UNIQUE") for row in cursor.fetchall()]
        finally:
            cursor.close()

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        """Get triggers from Oracle."""
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT owner, trigger_name, table_owner, table_name FROM all_triggers WHERE base_object_type = 'TABLE' ORDER BY owner, table_owner, table_name, trigger_name")
            return [TriggerInfo(name=_dictionary_qualified_name(row[0], row[1]), table_name=_dictionary_qualified_name(row[2], row[3]) if row[3] else "") for row in cursor.fetchall()]
        finally:
            cursor.close()

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        """Get sequences from Oracle."""
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT sequence_owner, sequence_name FROM all_sequences ORDER BY sequence_owner, sequence_name")
            return [SequenceInfo(name=_dictionary_qualified_name(row[0], row[1])) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def get_foreign_keys(
        self,
        conn: Any,
        table: str,
        database: str | None = None,
        schema: str | None = None,
    ) -> list[ForeignKeyInfo]:
        """List outgoing FKs via Oracle's accessible constraint metadata.

        Joins each FK's child column (uc) to its parent column (rc) via
        r_constraint_name. Oracle stores identifiers upper-case in the
        dictionary views unless quoted on creation.
        """
        owner_predicate = "c.owner = :owner_name" if schema else "c.owner = SYS_CONTEXT('USERENV', 'SESSION_USER')"
        params = {"table_name": table if schema else table.upper()}
        if schema:
            params["owner_name"] = schema
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT c.constraint_name, ucc.position, "
                "       ucc.column_name, rc.table_name, rcc.column_name, "
                "       c.owner, rc.owner "
                "FROM all_constraints c "
                "JOIN all_cons_columns ucc "
                "  ON c.owner = ucc.owner "
                "  AND c.constraint_name = ucc.constraint_name "
                "JOIN all_constraints rc "
                "  ON c.r_owner = rc.owner "
                "  AND c.r_constraint_name = rc.constraint_name "
                "JOIN all_cons_columns rcc "
                "  ON rc.owner = rcc.owner "
                "  AND rc.constraint_name = rcc.constraint_name "
                "  AND ucc.position = rcc.position "
                "WHERE c.constraint_type = 'R' "
                f"AND {owner_predicate} AND c.table_name = :table_name "
                "ORDER BY c.constraint_name, ucc.position",
                params,
            )
            return [
                ForeignKeyInfo(
                    owner_table=table,
                    column=row[2],
                    referenced_table=row[3],
                    referenced_column=row[4],
                    owner_schema=row[5],
                    referenced_schema=row[6],
                    constraint_name=row[0],
                    ordinal=int(row[1]),
                )
                for row in cursor.fetchall()
            ]
        finally:
            cursor.close()

    def get_referencing_foreign_keys(
        self,
        conn: Any,
        table: str,
        database: str | None = None,
        schema: str | None = None,
    ) -> list[ForeignKeyInfo]:
        """List FKs from other tables that reference `table`."""
        owner_predicate = "rc.owner = :owner_name" if schema else "rc.owner = SYS_CONTEXT('USERENV', 'SESSION_USER')"
        params = {"table_name": table if schema else table.upper()}
        if schema:
            params["owner_name"] = schema
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT c.constraint_name, ucc.position, "
                "       c.table_name, ucc.column_name, rcc.column_name, "
                "       c.owner, rc.owner "
                "FROM all_constraints c "
                "JOIN all_cons_columns ucc "
                "  ON c.owner = ucc.owner "
                "  AND c.constraint_name = ucc.constraint_name "
                "JOIN all_constraints rc "
                "  ON c.r_owner = rc.owner "
                "  AND c.r_constraint_name = rc.constraint_name "
                "JOIN all_cons_columns rcc "
                "  ON rc.owner = rcc.owner "
                "  AND rc.constraint_name = rcc.constraint_name "
                "  AND ucc.position = rcc.position "
                "WHERE c.constraint_type = 'R' "
                f"AND {owner_predicate} AND rc.table_name = :table_name "
                "ORDER BY c.table_name, c.constraint_name, ucc.position",
                params,
            )
            return [
                ForeignKeyInfo(
                    owner_table=row[2],
                    column=row[3],
                    referenced_table=table,
                    referenced_column=row[4],
                    owner_schema=row[5],
                    referenced_schema=row[6],
                    constraint_name=row[0],
                    ordinal=int(row[1]),
                )
                for row in cursor.fetchall()
            ]
        finally:
            cursor.close()

    def get_index_definition(self, conn: Any, index_name: str, table_name: str, database: str | None = None) -> dict[str, Any]:
        """Get detailed information about an Oracle index."""
        owner, bare_index = _split_dictionary_name(index_name)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT uniqueness, index_type FROM all_indexes WHERE index_name = :1 AND owner = COALESCE(:2, SYS_CONTEXT('USERENV', 'SESSION_USER'))",
                (bare_index, owner),
            )
            row = cursor.fetchone()
            is_unique = row[0] == "UNIQUE" if row else False
            index_type = row[1] if row else "NORMAL"
        finally:
            cursor.close()

        # Get index columns
        col_cursor = conn.cursor()
        try:
            col_cursor.execute(
                "SELECT column_name FROM all_ind_columns WHERE index_name = :1 AND index_owner = COALESCE(:2, SYS_CONTEXT('USERENV', 'SESSION_USER')) ORDER BY column_position",
                (bare_index, owner),
            )
            columns = [row[0] for row in col_cursor.fetchall()]
        finally:
            col_cursor.close()

        # Try to get DDL
        ddl_cursor = conn.cursor()
        try:
            ddl_cursor.execute(
                "SELECT DBMS_METADATA.GET_DDL('INDEX', :1, COALESCE(:2, SYS_CONTEXT('USERENV', 'SESSION_USER'))) FROM dual",
                (bare_index, owner),
            )
            ddl_row = ddl_cursor.fetchone()
            definition = str(ddl_row[0]) if ddl_row else None
        except Exception:
            definition = f"CREATE {'UNIQUE ' if is_unique else ''}INDEX {index_name} ON {table_name} ({', '.join(columns)})"
        finally:
            ddl_cursor.close()

        return {
            "name": index_name,
            "table_name": table_name,
            "columns": columns,
            "is_unique": is_unique,
            "type": index_type,
            "definition": definition,
        }

    def get_trigger_definition(self, conn: Any, trigger_name: str, table_name: str, database: str | None = None) -> dict[str, Any]:
        """Get detailed information about an Oracle trigger."""
        owner, bare_trigger = _split_dictionary_name(trigger_name)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT trigger_type, triggering_event, trigger_body FROM all_triggers WHERE trigger_name = :1 AND owner = COALESCE(:2, SYS_CONTEXT('USERENV', 'SESSION_USER'))",
                (bare_trigger, owner),
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
        finally:
            cursor.close()

    def get_sequence_definition(self, conn: Any, sequence_name: str, database: str | None = None) -> dict[str, Any]:
        """Get detailed information about an Oracle sequence."""
        owner, bare_sequence = _split_dictionary_name(sequence_name)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT min_value, max_value, increment_by, cycle_flag, last_number FROM all_sequences WHERE sequence_name = :1 AND sequence_owner = COALESCE(:2, SYS_CONTEXT('USERENV', 'SESSION_USER'))",
                (bare_sequence, owner),
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
        finally:
            cursor.close()

    def quote_identifier(self, name: str) -> str:
        """Quote identifier using double quotes for Oracle.

        Escapes embedded double quotes by doubling them.
        """
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        """Build a schema-aware SELECT query with Oracle 12c+ pagination."""
        qualified = self.catalog_qualified_name(database, schema, table)
        return f"SELECT * FROM {qualified} FETCH FIRST {limit} ROWS ONLY"

    def build_filtered_select_query(self, table: str, column: str, value: Any, limit: int, database: str | None = None, schema: str | None = None) -> str:
        qualified = self.catalog_qualified_name(database, schema, table)
        return f"SELECT * FROM {qualified} WHERE {self.quote_identifier(column)} = {self.quote_literal(value)} FETCH FIRST {limit} ROWS ONLY"

    def execute_query(self, conn: Any, query: str, max_rows: int | None = None) -> tuple[list[str], list[tuple], bool]:
        """Execute a query on Oracle with optional row limit."""
        cursor = conn.cursor()
        try:
            # Larger fetch batches cut per-round-trip overhead on high-latency
            # links without fetching beyond the requested result cap.
            row_budget = max_rows + 1 if max_rows is not None else 1001
            cursor.arraysize = min(1000, max(1, row_budget))
            cursor.prefetchrows = min(1001, max(1, row_budget))
            cursor.execute(_prepare_statement(query))
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
        finally:
            cursor.close()

    def execute_non_query(self, conn: Any, query: str) -> int:
        """Execute a non-query on Oracle."""
        cursor = conn.cursor()
        try:
            cursor.execute(_prepare_statement(query))
            rowcount = int(cursor.rowcount)
            conn.commit()
            return rowcount
        finally:
            cursor.close()
