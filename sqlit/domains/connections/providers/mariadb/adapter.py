"""MariaDB adapter using mariadb connector."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.adapters.base import (
    ColumnInfo,
    IndexInfo,
    SequenceInfo,
    TableInfo,
    TriggerInfo,
)
from sqlit.domains.connections.providers.mysql.base import MySQLBaseAdapter
from sqlit.domains.connections.providers.registry import get_default_port
from sqlit.domains.connections.providers.tls import (
    TLS_MODE_DEFAULT,
    TLS_MODE_DISABLE,
    get_tls_files,
    get_tls_mode,
    tls_mode_verifies_cert,
    tls_mode_verifies_hostname,
)

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


class MariaDBAdapter(MySQLBaseAdapter):
    """Adapter for MariaDB using mariadb connector.

    MariaDB uses ? placeholders instead of %s, so we override the
    introspection methods that use parameterized queries.
    """

    @property
    def name(self) -> str:
        return "MariaDB"

    @property
    def install_extra(self) -> str:
        return "mariadb"

    @property
    def install_package(self) -> str:
        return "mariadb"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("mariadb",)

    @property
    def supports_sequences(self) -> bool:
        """MariaDB 10.3+ supports sequences."""
        return getattr(self, "_supports_sequences", True)

    def get_post_connect_warnings(self, config: ConnectionConfig) -> list[str]:
        if self.supports_sequences:
            return []
        version = getattr(self, "_server_version_str", None)
        if isinstance(version, str) and version:
            return [f"MariaDB {version} does not support sequences (requires 10.3+)"]
        return ["MariaDB does not support sequences (requires 10.3+)"]

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to MariaDB database."""
        mariadb = self._import_driver_module(
            "mariadb",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        endpoint = config.tcp_endpoint
        if endpoint is None:
            raise ValueError("MariaDB connections require a TCP-style endpoint.")
        port = int(endpoint.port or get_default_port("mariadb"))
        mariadb_any: Any = mariadb
        connect_args: dict[str, Any] = {
            "host": endpoint.host,
            "port": port,
            "database": endpoint.database or None,
            "user": endpoint.username,
            "password": endpoint.password,
            "connect_timeout": 10,
        }

        tls_mode = get_tls_mode(config)
        tls_ca, tls_cert, tls_key, _ = get_tls_files(config)
        has_tls_files = any([tls_ca, tls_cert, tls_key])
        if tls_mode != TLS_MODE_DISABLE and (tls_mode != TLS_MODE_DEFAULT or has_tls_files):
            if tls_ca:
                connect_args["ssl_ca"] = tls_ca
            if tls_cert:
                connect_args["ssl_cert"] = tls_cert
            if tls_key:
                connect_args["ssl_key"] = tls_key
            if tls_mode != TLS_MODE_DEFAULT:
                connect_args["ssl_verify_cert"] = tls_mode_verifies_cert(tls_mode)
                connect_args["ssl_verify_identity"] = tls_mode_verifies_hostname(tls_mode)

        connect_args.update(config.extra_options)
        conn = mariadb_any.connect(**connect_args)

        # Note: The MariaDB Python connector only supports UTF-8 family charsets.
        # Legacy charsets like TIS-620 or Latin1 are not supported. For databases
        # using legacy charsets, use the MySQL provider with PyMySQL instead.

        self._supports_sequences = self._detect_sequences_support(conn)
        return conn

    def _detect_sequences_support(self, conn: Any) -> bool:
        """Determine whether the server supports sequences (MariaDB 10.3+)."""
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT VERSION()")
            row = cursor.fetchone()
        except Exception:
            return True

        if not row or not isinstance(row[0], str):
            return True

        self._server_version_str = row[0]
        match = re.match(r"^(\\d+)\\.(\\d+)(?:\\.(\\d+))?", row[0])
        if not match:
            return True

        major = int(match.group(1))
        minor = int(match.group(2))
        patch = int(match.group(3) or 0)
        return (major, minor, patch) >= (10, 3, 0)

    # MariaDB connector uses ? placeholders instead of %s, so override methods with params

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables from MariaDB. Returns (schema, name) with empty schema."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = ? AND table_type = 'BASE TABLE' "
                "ORDER BY table_name",
                (database,),
            )
        else:
            cursor.execute("SHOW TABLES")
        return [("", row[0]) for row in cursor.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of views from MariaDB. Returns (schema, name) with empty schema."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT table_name FROM information_schema.views " "WHERE table_schema = ? ORDER BY table_name",
                (database,),
            )
        else:
            cursor.execute(
                "SELECT table_name FROM information_schema.views " "WHERE table_schema = DATABASE() ORDER BY table_name"
            )
        return [("", row[0]) for row in cursor.fetchall()]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get columns for a table from MariaDB. Schema parameter is ignored."""
        cursor = conn.cursor()

        # Get primary key columns
        if database:
            cursor.execute(
                "SELECT column_name FROM information_schema.key_column_usage "
                "WHERE table_schema = ? AND table_name = ? AND constraint_name = 'PRIMARY'",
                (database, table),
            )
        else:
            cursor.execute(
                "SELECT column_name FROM information_schema.key_column_usage "
                "WHERE table_schema = DATABASE() AND table_name = ? AND constraint_name = 'PRIMARY'",
                (table,),
            )
        pk_columns = {row[0] for row in cursor.fetchall()}

        # Get all columns
        if database:
            cursor.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = ? AND table_name = ? "
                "ORDER BY ordinal_position",
                (database, table),
            )
        else:
            cursor.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = ? "
                "ORDER BY ordinal_position",
                (table,),
            )
        return [ColumnInfo(name=row[0], data_type=row[1], is_primary_key=row[0] in pk_columns) for row in cursor.fetchall()]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """Get stored procedures from MariaDB."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT routine_name FROM information_schema.routines "
                "WHERE routine_schema = ? AND routine_type = 'PROCEDURE' "
                "ORDER BY routine_name",
                (database,),
            )
        else:
            cursor.execute(
                "SELECT routine_name FROM information_schema.routines "
                "WHERE routine_schema = DATABASE() AND routine_type = 'PROCEDURE' "
                "ORDER BY routine_name"
            )
        return [row[0] for row in cursor.fetchall()]

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        """Get indexes from MariaDB (uses ? placeholders)."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT DISTINCT index_name, table_name, non_unique "
                "FROM information_schema.statistics "
                "WHERE table_schema = ? AND index_name != 'PRIMARY' "
                "ORDER BY table_name, index_name",
                (database,),
            )
        else:
            cursor.execute(
                "SELECT DISTINCT index_name, table_name, non_unique "
                "FROM information_schema.statistics "
                "WHERE table_schema = DATABASE() AND index_name != 'PRIMARY' "
                "ORDER BY table_name, index_name"
            )
        return [
            IndexInfo(name=row[0], table_name=row[1], is_unique=row[2] == 0)
            for row in cursor.fetchall()
        ]

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        """Get triggers from MariaDB (uses ? placeholders)."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT trigger_name, event_object_table "
                "FROM information_schema.triggers "
                "WHERE trigger_schema = ? "
                "ORDER BY event_object_table, trigger_name",
                (database,),
            )
        else:
            cursor.execute(
                "SELECT trigger_name, event_object_table "
                "FROM information_schema.triggers "
                "WHERE trigger_schema = DATABASE() "
                "ORDER BY event_object_table, trigger_name"
            )
        return [TriggerInfo(name=row[0], table_name=row[1]) for row in cursor.fetchall()]

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        """Get sequences from MariaDB 10.3+."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT sequence_name FROM information_schema.sequences "
                "WHERE sequence_schema = ? "
                "ORDER BY sequence_name",
                (database,),
            )
        else:
            cursor.execute(
                "SELECT sequence_name FROM information_schema.sequences "
                "WHERE sequence_schema = DATABASE() "
                "ORDER BY sequence_name"
            )
        return [SequenceInfo(name=row[0]) for row in cursor.fetchall()]

    def get_index_definition(
        self, conn: Any, index_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a MariaDB index (uses ? placeholders)."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT column_name, non_unique, index_type "
                "FROM information_schema.statistics "
                "WHERE table_schema = ? AND table_name = ? AND index_name = ? "
                "ORDER BY seq_in_index",
                (database, table_name, index_name),
            )
        else:
            cursor.execute(
                "SELECT column_name, non_unique, index_type "
                "FROM information_schema.statistics "
                "WHERE table_schema = DATABASE() AND table_name = ? AND index_name = ? "
                "ORDER BY seq_in_index",
                (table_name, index_name),
            )
        rows = cursor.fetchall()
        columns = [row[0] for row in rows]
        is_unique = rows[0][1] == 0 if rows else False
        index_type = rows[0][2] if rows else "BTREE"

        return {
            "name": index_name,
            "table_name": table_name,
            "columns": columns,
            "is_unique": is_unique,
            "type": index_type,
            "definition": f"CREATE {'UNIQUE ' if is_unique else ''}INDEX {index_name} ON {table_name} ({', '.join(columns)})",
        }

    def get_trigger_definition(
        self, conn: Any, trigger_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a MariaDB trigger (uses ? placeholders)."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT action_timing, event_manipulation, action_statement "
                "FROM information_schema.triggers "
                "WHERE trigger_schema = ? AND trigger_name = ?",
                (database, trigger_name),
            )
        else:
            cursor.execute(
                "SELECT action_timing, event_manipulation, action_statement "
                "FROM information_schema.triggers "
                "WHERE trigger_schema = DATABASE() AND trigger_name = ?",
                (trigger_name,),
            )
        row = cursor.fetchone()
        if row:
            return {
                "name": trigger_name,
                "table_name": table_name,
                "timing": row[0],
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
        """Get detailed information about a MariaDB sequence (uses ? placeholders)."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT start_value, increment, minimum_value, maximum_value, cycle_option "
                "FROM information_schema.sequences "
                "WHERE sequence_schema = ? AND sequence_name = ?",
                (database, sequence_name),
            )
        else:
            cursor.execute(
                "SELECT start_value, increment, minimum_value, maximum_value, cycle_option "
                "FROM information_schema.sequences "
                "WHERE sequence_schema = DATABASE() AND sequence_name = ?",
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
                "cycle": row[4] == 1,
            }
        return {
            "name": sequence_name,
            "start_value": None,
            "increment": None,
            "min_value": None,
            "max_value": None,
            "cycle": None,
        }
