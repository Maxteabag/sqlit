"""Microsoft SQL Server adapter using mssql-python."""

from __future__ import annotations

import struct
import weakref
from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.adapters.base import (
    ColumnInfo,
    DatabaseAdapter,
    ForeignKeyInfo,
    IndexInfo,
    SequenceInfo,
    TableInfo,
    TriggerInfo,
    _strip_leading_sql_comments,
)
from sqlit.domains.connections.providers.tls import (
    TLS_MODE_DEFAULT,
    TLS_MODE_DISABLE,
    get_tls_mode,
)

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import AuthType, ConnectionConfig

# ODBC connection attribute that lets us hand SQL Server a pre-acquired
# Entra access token instead of having the driver acquire one itself.
SQL_COPT_SS_ACCESS_TOKEN = 1256


def _build_access_token_struct(token: str) -> bytes:
    """Pack a JWT into the layout SQL_COPT_SS_ACCESS_TOKEN expects.

    SQL Server's ODBC driver wants a 4-byte little-endian length prefix
    followed by the token encoded as UTF-16-LE bytes. Same layout the
    mssql-python driver builds internally; we just produce it ourselves
    so we can skip the driver's redundant token acquisition.
    """
    token_bytes = token.encode("UTF-16-LE")
    return struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)


class AzureAdAuthError(Exception):
    """Raised when the Azure AD credential chain cannot produce a SQL token.

    Surfaces the actionable hint (e.g. "run 'az login'") that would otherwise
    be buried in the ODBC driver's generic "Login failed for user ''" error.
    """


def _format_azure_ad_hint(exc: Exception) -> str:
    """Build a short, actionable error message from a credential-chain failure.

    Picks out the most useful sub-error (typically the AzureCliCredential
    line saying "Please run 'az login'") and prepends a one-line hint.
    Falls back to the full message if no specific line stands out.
    """
    text = str(exc)
    primary = _first_actionable_line(text)
    hint = "Run 'az login' (or set AZURE_CLIENT_ID/SECRET/TENANT environment variables)."
    if primary:
        return f"Azure AD authentication failed.\n  {primary}\n{hint}"
    return f"Azure AD authentication failed.\n{hint}\n\nDetails:\n{text}"


def _first_actionable_line(text: str) -> str:
    """Return the most actionable line from the credential-chain dump.

    Walks the needles in priority order — "Please run 'az login'" beats
    everything else because it tells the user exactly what to do. Lower-signal
    lines like "Environment variables are not fully configured" are passive
    and don't make this list; if no high-signal needle matches, the caller
    falls back to dumping the full chain.
    """
    needles = (
        "Please run 'az login'",
        "Please run `az login`",
        "azd auth login",
        "Az.Account module",
    )
    lines = text.splitlines()
    for needle in needles:
        for line in lines:
            if needle in line:
                return line.strip()
    return ""


def _is_use_unsupported_error(exc: Exception) -> bool:
    """True for Azure SQL Database's refusal to run a USE statement."""
    return "USE statement is not supported" in str(exc)


class SQLServerAdapter(DatabaseAdapter):
    """Adapter for Microsoft SQL Server using the mssql-python driver."""

    def __init__(self) -> None:
        self._supports_cross_database_queries_override: bool | None = None
        # Azure SQL Database rejects USE, so metadata for a database other than
        # the one the connection is bound to needs its own connection. The
        # config a connection was opened with is kept so we can rebuild the
        # connection string with DATABASE= swapped; the extra connections are
        # keyed by (id(parent), lowercased database name).
        self._configs: dict[int, Any] = {}
        self._db_conns: dict[tuple[int, str], Any] = {}
        self._conn_refs: dict[int, Any] = {}

    @property
    def name(self) -> str:
        return "SQL Server"

    @property
    def install_extra(self) -> str:
        return "mssql"

    @property
    def install_package(self) -> str:
        # Package providing the SQL Server driver (no external ODBC manager required)
        return "mssql-python"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        # DB-API 2.0 compatible driver
        return ("mssql_python",)

    @property
    def supports_multiple_databases(self) -> bool:
        return True

    @property
    def supports_cross_database_queries(self) -> bool:
        if self._supports_cross_database_queries_override is not None:
            return self._supports_cross_database_queries_override
        return True

    @property
    def supports_stored_procedures(self) -> bool:
        return True

    def classify_query(self, query: str) -> bool:
        """Treat T-SQL procedure execution as potentially row-returning."""
        return self._is_procedure_call(query) or super().classify_query(query)

    @staticmethod
    def _is_procedure_call(query: str) -> bool:
        """Distinguish procedure calls from EXECUTE AS and dynamic SQL."""
        statement = _strip_leading_sql_comments(query)
        parts = statement.split(maxsplit=1)
        if not parts or parts[0].upper() not in {"EXEC", "EXECUTE"} or len(parts) == 1:
            return False
        target = _strip_leading_sql_comments(parts[1])
        if not target:
            return False
        upper_target = target.upper()
        if upper_target.split(maxsplit=1)[0] == "AS":
            return False
        if target.startswith(("(", "'", '"')) or upper_target.startswith("N'"):
            return False
        if target.startswith("@"):
            _return_variable, separator, procedure = target.partition("=")
            return bool(separator and procedure.strip())
        return True

    @property
    def system_databases(self) -> frozenset[str]:
        return frozenset({"master", "tempdb", "model", "msdb"})

    def build_connection_string(self, config: ConnectionConfig) -> str:
        return self._build_connection_string(config)

    def get_auth_type(self, config: ConnectionConfig) -> AuthType:
        from sqlit.domains.connections.domain.config import AuthType

        auth_type = config.get_option("auth_type", "sql")
        try:
            return AuthType(str(auth_type))
        except ValueError:
            return AuthType.SQL_SERVER

    def apply_database_override(self, config: ConnectionConfig, database: str) -> ConnectionConfig:
        return config.with_endpoint(database=database) if database else config

    @property
    def default_schema(self) -> str:
        return "dbo"

    @property
    def supports_sequences(self) -> bool:
        """SQL Server 2012+ supports sequences."""
        return True

    @property
    def supports_foreign_keys(self) -> bool:
        return True

    def normalize_config(self, config: ConnectionConfig) -> ConnectionConfig:
        auth_type = str(config.get_option("auth_type") or "sql")
        config.set_option("auth_type", auth_type)

        trusted_connection = config.get_option("trusted_connection")
        if trusted_connection is None:
            config.set_option("trusted_connection", auth_type == "windows")

        endpoint = config.tcp_endpoint
        if auth_type == "windows" and not config.get_option("trusted_connection") and endpoint and endpoint.username:
            config.set_option("auth_type", "sql")
            config.set_option("trusted_connection", False)

        auth_type = str(config.get_option("auth_type") or "sql")
        if endpoint and endpoint.password == "" and auth_type in ("sql", "ad_password"):
            endpoint.password = None

        return config

    def detect_capabilities(self, conn: Any, config: ConnectionConfig) -> None:
        """Detect Azure SQL variants that don't support cross-database queries."""
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT CAST(SERVERPROPERTY('EngineEdition') AS int)")
            row = cursor.fetchone()
            if row:
                engine_edition = int(row[0])
                if engine_edition in (5, 6):
                    self._supports_cross_database_queries_override = False
        except Exception:
            pass

    def _build_connection_string(self, config: ConnectionConfig, *, attach_token: bool = False) -> str:
        """Build mssql-python connection string from config.

        Args:
            config: Connection configuration.
            attach_token: True when we'll be supplying SQL_COPT_SS_ACCESS_TOKEN
                ourselves. In that case omit the `Authentication=` directive —
                the two paths conflict, and the directive would make the driver
                spawn `az` to acquire its own token, defeating the optimization.

        Returns:
            semicolon-delimited key=value connection string.
        """
        from sqlit.domains.connections.domain.config import AuthType

        endpoint = config.tcp_endpoint
        if endpoint is None:
            raise ValueError("SQL Server connections require a TCP-style endpoint.")
        server_with_port = endpoint.host
        if endpoint.port and endpoint.port != "1433":
            server_with_port = f"{endpoint.host},{endpoint.port}"

        base = f"SERVER={server_with_port};" f"DATABASE={endpoint.database or 'master'};"

        tls_mode = get_tls_mode(config)
        trust_value = str(config.get_option("tls_trust_server_certificate", "yes")).lower()
        trust_server_cert = "no" if trust_value in {"no", "false", "0"} else "yes"

        security_parts: list[str] = []
        if tls_mode != TLS_MODE_DEFAULT:
            encrypt_value = "no" if tls_mode == TLS_MODE_DISABLE else "yes"
            security_parts.append(f"Encrypt={encrypt_value};")
        security_parts.append(f"TrustServerCertificate={trust_server_cert};")

        base = base + "".join(security_parts)

        auth = self.get_auth_type(config)

        if attach_token and auth == AuthType.AD_DEFAULT:
            return base

        if auth == AuthType.WINDOWS:
            return base + "Trusted_Connection=yes;"
        elif auth == AuthType.SQL_SERVER:
            return base + f"Authentication=SqlPassword;" f"UID={endpoint.username};PWD={endpoint.password};"
        elif auth == AuthType.AD_PASSWORD:
            return base + f"Authentication=ActiveDirectoryPassword;" f"UID={endpoint.username};PWD={endpoint.password};"
        elif auth == AuthType.AD_INTERACTIVE:
            return base + f"Authentication=ActiveDirectoryInteractive;" f"UID={endpoint.username};"
        elif auth == AuthType.AD_INTEGRATED:
            return base + "Authentication=ActiveDirectoryIntegrated;"
        elif auth == AuthType.AD_DEFAULT:
            # Uses Azure CLI / environment credentials automatically
            return base + "Authentication=ActiveDirectoryDefault;"

        return base + "Trusted_Connection=yes;"

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to SQL Server using the mssql-python driver."""
        mssql_python = self._import_driver_module(
            "mssql_python",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        token = self._preflight_azure_credentials(config)

        conn_str = self._build_connection_string(config, attach_token=token is not None)
        # Append extra_options to connection string
        for key, value in config.extra_options.items():
            conn_str += f"{key}={value};"

        attrs_before: dict[int, bytes] | None = None
        if token is not None:
            attrs_before = {SQL_COPT_SS_ACCESS_TOKEN: _build_access_token_struct(token)}

        conn = mssql_python.connect(conn_str, attrs_before=attrs_before)
        # Enable autocommit to allow DDL statements like CREATE DATABASE
        conn.autocommit = True
        self._track(conn, config)
        return conn

    def _track(self, conn: Any, config: ConnectionConfig) -> None:
        """Remember the config a connection was opened with.

        Entries are keyed by id(), so they have to go before the id can be
        handed to a different object: a weakref callback drops them when the
        connection is collected without an explicit disconnect(). Drivers whose
        connection objects don't support weak references keep the entry until
        disconnect() clears it.
        """
        key = id(conn)
        try:
            self._conn_refs[key] = weakref.ref(conn, lambda _ref, key=key: self._forget(key))
        except TypeError:
            pass
        self._configs[key] = config

    def _forget(self, parent_id: int) -> None:
        """Drop the bookkeeping for a connection and its per-database siblings."""
        for key in [k for k in self._db_conns if k[0] == parent_id]:
            sibling = self._db_conns.pop(key)
            self._forget(id(sibling))
            try:
                sibling.close()
            except Exception:
                pass
        self._configs.pop(parent_id, None)
        self._conn_refs.pop(parent_id, None)

    def disconnect(self, conn: Any) -> None:
        """Close the connection plus any per-database siblings opened for it."""
        self._forget(id(conn))
        super().disconnect(conn)

    def _preflight_azure_credentials(self, config: ConnectionConfig) -> str | None:
        """Acquire a SQL Entra token and return it for direct ODBC attach.

        Returning the JWT lets `connect()` hand it to the driver via
        SQL_COPT_SS_ACCESS_TOKEN, eliminating the duplicate token acquisition
        the driver would otherwise do when it sees `Authentication=...` in the
        connection string. Returns None if azure-identity isn't installed or
        the config isn't ad_default — falls back to driver-side auth.

        A persistent file cache (~5 minute refresh-before-expiry buffer)
        avoids spawning `az account get-access-token` on every invocation,
        which dominates cold-start cost for one-shot `sqlit query` runs.

        Failures surface as AzureAdAuthError with an actionable hint
        ("Please run 'az login'", etc.) instead of the driver's generic
        "Login failed for user ''".
        """
        import logging

        from sqlit.domains.connections.domain.config import AuthType

        if self.get_auth_type(config) != AuthType.AD_DEFAULT:
            return None
        try:
            from azure.core.exceptions import ClientAuthenticationError
            from azure.identity import DefaultAzureCredential
        except ImportError:
            return None

        from . import token_cache

        cached = token_cache.load()
        if cached is not None:
            return cached.token

        # azure-identity logs the full credential-chain dump to stderr at
        # WARNING level on failure. Our own error already names the actionable
        # cause, so silence the library's noise for the duration of this call.
        azure_logger = logging.getLogger("azure.identity")
        prior_level = azure_logger.level
        azure_logger.setLevel(logging.ERROR)
        try:
            access_token = DefaultAzureCredential().get_token(
                "https://database.windows.net/.default"
            )
        except ClientAuthenticationError as exc:
            raise AzureAdAuthError(_format_azure_ad_hint(exc)) from exc
        finally:
            azure_logger.setLevel(prior_level)

        try:
            token_cache.save(access_token.token, access_token.expires_on)
        except OSError:
            # Cache write failures are non-fatal — we still have the token.
            pass

        return access_token.token

    def get_databases(self, conn: Any) -> list[str]:
        """Get list of databases from SQL Server."""
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sys.databases ORDER BY name")
        return [row[0] for row in cursor.fetchall()]

    def _get_cursor_for_database(self, conn: Any, database: str | None) -> Any:
        """Get a cursor scoped to `database`.

        On a normal SQL Server instance that is a `USE`. Azure SQL Database
        (EngineEdition 5/6) rejects USE outright — "USE statement is not
        supported to switch between databases" — so there we open a second
        connection bound to the target database and cache it per parent
        connection. The first rejected USE also flips the cross-database
        capability off, so later calls skip straight to the sibling path even
        when detect_capabilities never ran (the process worker reads
        capabilities before it connects).
        """
        if not database:
            return conn.cursor()

        if self._connection_database(conn) == database.lower():
            return conn.cursor()

        if self.supports_cross_database_queries:
            cursor = conn.cursor()
            try:
                cursor.execute(f"USE [{database}]")
            except Exception as exc:
                if not _is_use_unsupported_error(exc):
                    raise
                self._supports_cross_database_queries_override = False
            else:
                return cursor

        target = self._connection_for_database(conn, database)
        return target.cursor()

    def _connection_database(self, conn: Any) -> str:
        """Lowercased database the connection was opened against, or ''."""
        config = self._configs.get(id(conn))
        endpoint = config.tcp_endpoint if config is not None else None
        return (endpoint.database or "").lower() if endpoint is not None else ""

    def _connection_for_database(self, conn: Any, database: str) -> Any:
        """Return a connection bound to `database`, opening one if needed."""
        key = (id(conn), database.lower())
        cached = self._db_conns.get(key)
        if cached is not None:
            return cached

        config = self._configs.get(id(conn))
        if config is None:
            # Connection came from somewhere other than our connect() — nothing
            # to rebuild a connection string from, so USE is the only option.
            cursor = conn.cursor()
            cursor.execute(f"USE [{database}]")
            return conn

        sibling = self.connect(self.apply_database_override(config, database))
        self._db_conns[key] = sibling
        return sibling

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables with schema from SQL Server."""
        cursor = self._get_cursor_for_database(conn, database)
        cursor.execute(
            "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_SCHEMA, TABLE_NAME"
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of views with schema from SQL Server."""
        cursor = self._get_cursor_for_database(conn, database)
        cursor.execute(
            "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.VIEWS "
            "ORDER BY TABLE_SCHEMA, TABLE_NAME"
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get columns for a table from SQL Server."""
        cursor = self._get_cursor_for_database(conn, database)
        schema = schema or "dbo"

        # Get primary key columns
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
        cursor.execute(
            "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
            (schema, table),
        )
        return [ColumnInfo(name=row[0], data_type=row[1], is_primary_key=row[0] in pk_columns) for row in cursor.fetchall()]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """Get stored procedures from SQL Server."""
        cursor = self._get_cursor_for_database(conn, database)
        cursor.execute(
            "SELECT ROUTINE_NAME FROM INFORMATION_SCHEMA.ROUTINES "
            "WHERE ROUTINE_TYPE = 'PROCEDURE' ORDER BY ROUTINE_NAME"
        )
        return [row[0] for row in cursor.fetchall()]

    def get_completion_routines(
        self, conn: Any, database: str | None = None
    ) -> list[Any]:
        """Get procedures/functions with parameter metadata for autocomplete."""
        from sqlit.domains.connections.providers.adapters.base import RoutineInfo

        cursor = self._get_cursor_for_database(conn, database)
        cursor.execute(
            "SELECT r.ROUTINE_SCHEMA, r.ROUTINE_NAME, r.ROUTINE_TYPE, r.DATA_TYPE, "
            "p.PARAMETER_NAME, p.ORDINAL_POSITION "
            "FROM INFORMATION_SCHEMA.ROUTINES r "
            "LEFT JOIN INFORMATION_SCHEMA.PARAMETERS p "
            "ON p.SPECIFIC_SCHEMA = r.SPECIFIC_SCHEMA "
            "AND p.SPECIFIC_NAME = r.SPECIFIC_NAME "
            "ORDER BY r.ROUTINE_SCHEMA, r.ROUTINE_NAME, p.ORDINAL_POSITION"
        )

        grouped: dict[tuple[str, str, str, str], list[str]] = {}
        for schema, name, routine_type, return_type, parameter, ordinal in cursor.fetchall():
            key = (schema, name, routine_type, return_type or "")
            if parameter and (ordinal is None or ordinal > 0):
                grouped.setdefault(key, []).append(parameter)
            else:
                grouped.setdefault(key, [])

        return [
            RoutineInfo(
                name,
                schema=schema,
                database=database or "",
                routine_type=routine_type,
                return_type=return_type,
                parameters=tuple(parameters),
            )
            for (schema, name, routine_type, return_type), parameters in grouped.items()
        ]

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        """Get indexes from SQL Server."""
        cursor = self._get_cursor_for_database(conn, database)
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
        cursor = self._get_cursor_for_database(conn, database)
        cursor.execute(
            "SELECT tr.name, OBJECT_NAME(tr.parent_id) "
            "FROM sys.triggers tr "
            "WHERE tr.is_ms_shipped = 0 AND tr.parent_id > 0 "
            "ORDER BY OBJECT_NAME(tr.parent_id), tr.name"
        )
        return [TriggerInfo(name=row[0], table_name=row[1] or "") for row in cursor.fetchall()]

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        """Get sequences from SQL Server (2012+)."""
        cursor = self._get_cursor_for_database(conn, database)
        cursor.execute("SELECT name FROM sys.sequences ORDER BY name")
        return [SequenceInfo(name=row[0]) for row in cursor.fetchall()]

    def get_foreign_keys(
        self,
        conn: Any,
        table: str,
        database: str | None = None,
        schema: str | None = None,
    ) -> list[ForeignKeyInfo]:
        """List outgoing FKs via sys.foreign_keys + sys.foreign_key_columns."""
        cursor = self._get_cursor_for_database(conn, database)
        schema = schema or self.default_schema
        cursor.execute(
            "SELECT fk.name, fkc.constraint_column_id, "
            "       pc.name, SCHEMA_NAME(rt.schema_id), rt.name, rc.name "
            "FROM sys.foreign_keys fk "
            "JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id "
            "JOIN sys.tables pt ON fk.parent_object_id = pt.object_id "
            "JOIN sys.columns pc ON pc.object_id = pt.object_id "
            "  AND pc.column_id = fkc.parent_column_id "
            "JOIN sys.tables rt ON fk.referenced_object_id = rt.object_id "
            "JOIN sys.columns rc ON rc.object_id = rt.object_id "
            "  AND rc.column_id = fkc.referenced_column_id "
            "WHERE SCHEMA_NAME(pt.schema_id) = ? AND pt.name = ? "
            "ORDER BY fk.name, fkc.constraint_column_id",
            (schema, table),
        )
        return [
            ForeignKeyInfo(
                owner_table=table,
                column=row[2],
                referenced_table=row[4],
                referenced_column=row[5],
                owner_schema=schema,
                referenced_schema=row[3] or "",
                constraint_name=row[0],
                ordinal=int(row[1]),
            )
            for row in cursor.fetchall()
        ]

    def get_referencing_foreign_keys(
        self,
        conn: Any,
        table: str,
        database: str | None = None,
        schema: str | None = None,
    ) -> list[ForeignKeyInfo]:
        """List FKs from other tables that reference `table`."""
        cursor = self._get_cursor_for_database(conn, database)
        schema = schema or self.default_schema
        cursor.execute(
            "SELECT fk.name, fkc.constraint_column_id, "
            "       SCHEMA_NAME(pt.schema_id), pt.name, pc.name, rc.name "
            "FROM sys.foreign_keys fk "
            "JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id "
            "JOIN sys.tables pt ON fk.parent_object_id = pt.object_id "
            "JOIN sys.columns pc ON pc.object_id = pt.object_id "
            "  AND pc.column_id = fkc.parent_column_id "
            "JOIN sys.tables rt ON fk.referenced_object_id = rt.object_id "
            "JOIN sys.columns rc ON rc.object_id = rt.object_id "
            "  AND rc.column_id = fkc.referenced_column_id "
            "WHERE SCHEMA_NAME(rt.schema_id) = ? AND rt.name = ? "
            "ORDER BY SCHEMA_NAME(pt.schema_id), pt.name, "
            "         fk.name, fkc.constraint_column_id",
            (schema, table),
        )
        return [
            ForeignKeyInfo(
                owner_table=row[3],
                column=row[4],
                referenced_table=table,
                referenced_column=row[5],
                owner_schema=row[2] or "",
                referenced_schema=schema,
                constraint_name=row[0],
                ordinal=int(row[1]),
            )
            for row in cursor.fetchall()
        ]

    def get_index_definition(
        self, conn: Any, index_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a SQL Server index."""
        cursor = self._get_cursor_for_database(conn, database)
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
            "definition": (
                f"CREATE {'UNIQUE ' if is_unique else ''}{index_type} INDEX "
                f"[{index_name}] ON [{table_name}] ({', '.join(f'[{c}]' for c in columns)})"
            ),
        }

    def get_trigger_definition(
        self, conn: Any, trigger_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a SQL Server trigger."""
        cursor = self._get_cursor_for_database(conn, database)
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
        cursor = self._get_cursor_for_database(conn, database)
        cursor.execute(
            "SELECT CAST(start_value AS BIGINT), CAST(increment AS BIGINT), "
            "CAST(minimum_value AS BIGINT), CAST(maximum_value AS BIGINT), is_cycling "
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
        """Build SELECT TOP query for SQL Server.

        Note: Does not include database prefix as Azure SQL Database doesn't
        support cross-database references. The caller should ensure the
        connection is to the correct database.
        """
        schema = schema or "dbo"
        return f"SELECT TOP {limit} * FROM [{schema}].[{table}]"

    def build_filtered_select_query(self, table: str, column: str, value: Any, limit: int, database: str | None = None, schema: str | None = None) -> str:
        qualified = self.catalog_qualified_name(database, schema, table)
        return f"SELECT TOP {limit} * FROM {qualified} WHERE {self.quote_identifier(column)} = {self.quote_literal(value)}"

    def quote_literal(self, value: Any) -> str:
        """Render SQL Server bit and binary literals using T-SQL syntax."""
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, bytes | bytearray | memoryview):
            return "0x" + bytes(value).hex()
        return super().quote_literal(value)

    def execute_query(self, conn: Any, query: str, max_rows: int | None = None) -> tuple[list[str], list[tuple], bool]:
        """Execute a query on SQL Server with optional row limit."""
        cursor = conn.cursor()
        cursor.execute(query)
        if self._is_procedure_call(query):
            result: tuple[list[str], list[tuple], bool] | None = None
            while True:
                if cursor.description and result is None:
                    columns = [col[0] for col in cursor.description]
                    if max_rows is not None:
                        rows = cursor.fetchmany(max_rows + 1)
                        truncated = len(rows) > max_rows
                        rows = rows[:max_rows]
                    else:
                        rows = cursor.fetchall()
                        truncated = False
                    result = (columns, [tuple(row) for row in rows], truncated)

                nextset = getattr(cursor, "nextset", None)
                if not callable(nextset) or not nextset():
                    break
            return result or ([], [], False)

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
