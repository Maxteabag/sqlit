"""Exasol adapter using pyexasol."""

from __future__ import annotations

import ssl
from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.adapters.base import (
    ColumnInfo,
    DatabaseAdapter,
    IndexInfo,
    SequenceInfo,
    TableInfo,
    TriggerInfo,
)
from sqlit.domains.connections.providers.registry import get_default_port
from sqlit.domains.connections.providers.tls import (
    TLS_MODE_DISABLE,
    get_tls_files,
    get_tls_mode,
    tls_mode_verifies_cert,
)

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


class ExasolAdapter(DatabaseAdapter):
    """Adapter for Exasol using pyexasol.

    pyexasol is a native WebSocket client rather than a DB-API 2.0 driver: it has
    no ``cursor()``, so this subclasses ``DatabaseAdapter`` directly and implements
    query execution against the ``ExaStatement`` returned by ``conn.execute()``.
    """

    @property
    def name(self) -> str:
        return "Exasol"

    @property
    def install_extra(self) -> str:
        return "exasol"

    @property
    def install_package(self) -> str:
        return "pyexasol"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("pyexasol",)

    @property
    def supports_multiple_databases(self) -> bool:
        # Exasol has no database layer above schemas.
        return False

    @property
    def supports_cross_database_queries(self) -> bool:
        return False

    @property
    def supports_stored_procedures(self) -> bool:
        # Exposed from EXA_ALL_SCRIPTS.
        return True

    @property
    def supports_indexes(self) -> bool:
        # Exasol indexes are auto-managed and unnamed.
        return False

    @property
    def supports_triggers(self) -> bool:
        # Exasol has no triggers.
        return False

    @property
    def supports_sequences(self) -> bool:
        # Exasol uses IDENTITY columns instead of sequences.
        return False

    @property
    def default_schema(self) -> str:
        # No universal default; every table stays schema-qualified.
        return ""

    def _tls_args(self, config: ConnectionConfig) -> dict[str, Any]:
        """Map the shared tls_mode option onto pyexasol encryption kwargs.

        Since pyexasol 1.0.0 an omitted websocket_sslopt means CERT_REQUIRED, but
        exasol/docker-db and most on-premise installations present a self-signed
        certificate, so deferring to that driver default fails every out-of-the-box
        connect. The default mode therefore encrypts without verifying, matching how
        the other providers here treat it; verification starts at verify-ca.
        """
        tls_mode = get_tls_mode(config)
        if tls_mode == TLS_MODE_DISABLE:
            return {"encryption": False}
        if not tls_mode_verifies_cert(tls_mode):
            return {"encryption": True, "websocket_sslopt": {"cert_reqs": ssl.CERT_NONE}}

        sslopt: dict[str, Any] = {"cert_reqs": ssl.CERT_REQUIRED}
        tls_ca, tls_cert, tls_key, _ = get_tls_files(config)
        if tls_ca:
            sslopt["ca_certs"] = tls_ca
        if tls_cert:
            sslopt["certfile"] = tls_cert
        if tls_key:
            sslopt["keyfile"] = tls_key
        return {"encryption": True, "websocket_sslopt": sslopt}

    def connect(self, config: ConnectionConfig) -> Any:
        endpoint = config.tcp_endpoint
        if endpoint is None:
            raise ValueError("Exasol connections require a TCP-style endpoint.")

        pyexasol = self._import_driver_module(
            "pyexasol",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        port = int(endpoint.port or get_default_port("exasol"))
        connect_args: dict[str, Any] = {
            "dsn": f"{endpoint.host}:{port}",
            "schema": config.get_option("schema", ""),
            "autocommit": True,
        }

        # Add only the selected method's credentials: pyexasol's login branches on
        # token presence, so a stray access_token/refresh_token key changes the
        # auth path rather than being ignored.
        authenticator = config.get_option("authenticator", "password")
        if authenticator == "access_token":
            connect_args["access_token"] = config.get_option("access_token", "")
        elif authenticator == "refresh_token":
            connect_args["refresh_token"] = config.get_option("refresh_token", "")
        else:
            connect_args["user"] = endpoint.username
            connect_args["password"] = endpoint.password

        connect_args.update(self._tls_args(config))
        connect_args.update(config.extra_options)
        return pyexasol.connect(**connect_args)

    def get_databases(self, conn: Any) -> list[str]:
        # Exasol has no database layer above schemas.
        return []

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        # conn.meta.* wraps every query in Exasol's snapshot-execution hint, so it
        # cannot be blocked by metadata locks. The list_* helpers return already
        # fetched lists of dicts with UPPERCASE keys - pyexasol enforces
        # fetch_dict=True there - so rows must be read by key, never by index.
        return [(row["TABLE_SCHEMA"], row["TABLE_NAME"]) for row in conn.meta.list_tables()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        return [(row["VIEW_SCHEMA"], row["VIEW_NAME"]) for row in conn.meta.list_views()]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        schema = schema or ""

        # Unlike the list_* helpers, execute_snapshot returns an ExaStatement,
        # so it needs an explicit fetchall().
        pk_rows = conn.meta.execute_snapshot(
            "SELECT COLUMN_NAME FROM SYS.EXA_ALL_CONSTRAINT_COLUMNS "
            "WHERE CONSTRAINT_TYPE = 'PRIMARY KEY' "
            "AND CONSTRAINT_SCHEMA = {schema!s} AND CONSTRAINT_TABLE = {table!s}",
            {"schema": schema, "table": table},
        ).fetchall()
        pk_columns = {row["COLUMN_NAME"] for row in pk_rows}

        return [
            ColumnInfo(
                name=row["COLUMN_NAME"],
                data_type=row["COLUMN_TYPE"],
                is_primary_key=row["COLUMN_NAME"] in pk_columns,
            )
            for row in conn.meta.list_columns(schema, table)
        ]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        # SCRIPTING is Exasol's scripting-program type, as opposed to UDF,
        # ADAPTER and PREPROCESSOR.
        rows = conn.meta.execute_snapshot(
            "SELECT SCRIPT_SCHEMA, SCRIPT_NAME FROM SYS.EXA_ALL_SCRIPTS "
            "WHERE SCRIPT_TYPE = 'SCRIPTING' "
            "ORDER BY SCRIPT_SCHEMA, SCRIPT_NAME"
        ).fetchall()
        return [row["SCRIPT_NAME"] for row in rows]

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        # Exasol indexes are auto-managed and unnamed.
        return []

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        # Exasol has no triggers.
        return []

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        # Exasol uses IDENTITY columns instead of sequences.
        return []

    def quote_identifier(self, name: str) -> str:
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        quoted_table = self.quote_identifier(table)
        if schema:
            return f"SELECT * FROM {self.quote_identifier(schema)}.{quoted_table} LIMIT {limit}"
        return f"SELECT * FROM {quoted_table} LIMIT {limit}"

    def execute_test_query(self, conn: Any) -> None:
        # The inherited implementation calls conn.cursor(), which pyexasol lacks.
        conn.execute(self.test_query).fetchval()

    def execute_query(self, conn: Any, query: str, max_rows: int | None = None) -> tuple[list[str], list[tuple], bool]:
        stmt = conn.execute(query)

        # This guard must precede any fetch: ExaStatement.__next__ raises
        # ExaRuntimeError ("Attempt to fetch from statement without result set")
        # for a rowCount statement, and fetchmany() iterates.
        if stmt.result_type != "resultSet":
            return [], [], False

        columns = list(stmt.column_names())
        if max_rows is None:
            return columns, [tuple(row) for row in stmt.fetchall()], False

        # Fetch one row beyond the limit to detect truncation, then trim.
        rows = stmt.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        return columns, [tuple(row) for row in rows[:max_rows]], truncated

    def execute_non_query(self, conn: Any, query: str) -> int:
        # rowcount is a method on ExaStatement, not a property. No explicit
        # commit: the connection is opened with autocommit=True.
        return int(conn.execute(query).rowcount())
