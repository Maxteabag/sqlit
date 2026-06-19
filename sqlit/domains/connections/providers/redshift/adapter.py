"""Amazon Redshift adapter using redshift_connector."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.adapters.base import (
    ColumnInfo,
    CursorBasedAdapter,
    ForeignKeyInfo,
    IndexInfo,
    SequenceInfo,
    TableInfo,
    TriggerInfo,
)
from sqlit.domains.connections.providers.tls import (
    TLS_MODE_DEFAULT,
    TLS_MODE_DISABLE,
    get_tls_files,
    get_tls_mode,
)

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


class RedshiftAdapter(CursorBasedAdapter):
    """Adapter for Amazon Redshift."""

    @property
    def name(self) -> str:
        return "Redshift"

    @property
    def install_extra(self) -> str:
        return "redshift"

    @property
    def install_package(self) -> str:
        return "redshift-connector"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("redshift_connector",)

    @property
    def supports_multiple_databases(self) -> bool:
        return True

    @property
    def supports_stored_procedures(self) -> bool:
        return True

    @property
    def supports_triggers(self) -> bool:
        return False

    @property
    def supports_indexes(self) -> bool:
        return False  # Redshift uses sort keys instead of indexes

    @property
    def supports_foreign_keys(self) -> bool:
        # FKs are informational only (not enforced) but queryable via pg_catalog.
        return True

    @property
    def supports_cross_database_queries(self) -> bool:
        return True

    def apply_database_override(self, config: ConnectionConfig, database: str) -> ConnectionConfig:
        """Apply a default database for unqualified queries."""
        if not database:
            return config
        return config.with_endpoint(database=database)

    @property
    def system_databases(self) -> frozenset[str]:
        return frozenset({"template0", "template1", "padb_harvest"})

    @property
    def default_schema(self) -> str:
        return "public"

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to Amazon Redshift."""
        redshift_connector = self._import_driver_module(
            "redshift_connector",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        auth_method = config.options.get("redshift_auth_method", "password")
        endpoint = config.tcp_endpoint
        if endpoint is None:
            raise ValueError("Redshift connections require a TCP-style endpoint.")

        connect_args: dict[str, Any] = {
            "host": endpoint.host,
            "port": int(endpoint.port or "5439"),
            "database": endpoint.database or "dev",
        }

        if auth_method == "iam":
            # IAM authentication
            connect_args["iam"] = True
            connect_args["db_user"] = endpoint.username
            connect_args["cluster_identifier"] = config.options.get("redshift_cluster_id")
            connect_args["region"] = config.options.get("redshift_region", "us-east-1")
            if config.options.get("redshift_profile"):
                connect_args["profile"] = config.options["redshift_profile"]
        else:
            # Standard password authentication
            connect_args["user"] = endpoint.username
            connect_args["password"] = endpoint.password

        tls_mode = get_tls_mode(config)
        tls_ca, tls_cert, tls_key, _ = get_tls_files(config)
        has_tls_files = any([tls_ca, tls_cert, tls_key])
        if tls_mode == TLS_MODE_DISABLE:
            connect_args["ssl"] = False
        elif tls_mode != TLS_MODE_DEFAULT or has_tls_files:
            connect_args["ssl"] = True
            if tls_mode != TLS_MODE_DEFAULT:
                connect_args["sslmode"] = tls_mode
            if tls_ca:
                connect_args["sslrootcert"] = tls_ca
            if tls_cert:
                connect_args["sslcert"] = tls_cert
            if tls_key:
                connect_args["sslkey"] = tls_key

        connect_args.update(config.extra_options)
        conn = redshift_connector.connect(**connect_args)
        conn.autocommit = True
        return conn

    def get_databases(self, conn: Any) -> list[str]:
        """Get list of databases from Redshift."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT datname FROM pg_database "
            "WHERE datistemplate = false ORDER BY datname"
        )
        return [row[0] for row in cursor.fetchall()]

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT schemaname, tablename FROM pg_tables "
            "WHERE schemaname NOT IN ('pg_catalog', 'information_schema', 'pg_internal') "
            "ORDER BY schemaname, tablename"
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of views."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT schemaname, viewname FROM pg_views "
            "WHERE schemaname NOT IN ('pg_catalog', 'information_schema', 'pg_internal') "
            "ORDER BY schemaname, viewname"
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get columns for a table."""
        cursor = conn.cursor()
        schema = schema or self.default_schema

        # Get column info including sort key info (Redshift's equivalent of primary key)
        cursor.execute(
            """
            SELECT
                c.column_name,
                c.data_type,
                CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END as is_pk
            FROM information_schema.columns c
            LEFT JOIN (
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                WHERE tc.table_schema = %s
                    AND tc.table_name = %s
                    AND tc.constraint_type = 'PRIMARY KEY'
            ) pk ON c.column_name = pk.column_name
            WHERE c.table_schema = %s AND c.table_name = %s
            ORDER BY c.ordinal_position
            """,
            (schema, table, schema, table),
        )

        return [
            ColumnInfo(name=row[0], data_type=row[1], is_primary_key=row[2])
            for row in cursor.fetchall()
        ]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """Get stored procedures from Redshift."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT proname FROM pg_proc p "
            "JOIN pg_namespace n ON p.pronamespace = n.oid "
            "WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY proname"
        )
        return [row[0] for row in cursor.fetchall()]

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        """Redshift doesn't have traditional indexes."""
        return []

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        """Redshift doesn't support triggers."""
        return []

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        """Get sequences from Redshift."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT sequence_name FROM information_schema.sequences "
            "WHERE sequence_schema NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY sequence_name"
        )
        return [SequenceInfo(name=row[0]) for row in cursor.fetchall()]

    def get_foreign_keys(
        self,
        conn: Any,
        table: str,
        database: str | None = None,
        schema: str | None = None,
    ) -> list[ForeignKeyInfo]:
        """Outgoing FKs via pg_catalog.

        Redshift's `information_schema` is often incomplete; query pg_catalog
        directly. `generate_series` over conkey/confkey expands composite FKs
        into one row per column pair.
        """
        cursor = conn.cursor()
        schema = (schema or "public").lower()
        cursor.execute(
            "SELECT c.conname, k.n, af.attname, "
            "       rn.nspname, rt.relname, ar.attname "
            "FROM pg_constraint c "
            "JOIN pg_class t  ON t.oid  = c.conrelid "
            "JOIN pg_namespace n ON n.oid = t.relnamespace "
            "JOIN pg_class rt ON rt.oid = c.confrelid "
            "JOIN pg_namespace rn ON rn.oid = rt.relnamespace "
            "JOIN generate_series(1, array_upper(c.conkey, 1)) AS k(n) ON TRUE "
            "JOIN pg_attribute af ON af.attrelid = t.oid  AND af.attnum = c.conkey[k.n] "
            "JOIN pg_attribute ar ON ar.attrelid = rt.oid AND ar.attnum = c.confkey[k.n] "
            "WHERE c.contype = 'f' AND n.nspname = %s AND t.relname = %s "
            "ORDER BY c.conname, k.n",
            (schema, table.lower()),
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
        cursor = conn.cursor()
        schema = (schema or "public").lower()
        cursor.execute(
            "SELECT c.conname, k.n, af.attname, "
            "       n.nspname, t.relname, ar.attname "
            "FROM pg_constraint c "
            "JOIN pg_class t  ON t.oid  = c.conrelid "
            "JOIN pg_namespace n ON n.oid = t.relnamespace "
            "JOIN pg_class rt ON rt.oid = c.confrelid "
            "JOIN pg_namespace rn ON rn.oid = rt.relnamespace "
            "JOIN generate_series(1, array_upper(c.conkey, 1)) AS k(n) ON TRUE "
            "JOIN pg_attribute af ON af.attrelid = t.oid  AND af.attnum = c.conkey[k.n] "
            "JOIN pg_attribute ar ON ar.attrelid = rt.oid AND ar.attnum = c.confkey[k.n] "
            "WHERE c.contype = 'f' AND rn.nspname = %s AND rt.relname = %s "
            "ORDER BY n.nspname, t.relname, c.conname, k.n",
            (schema, table.lower()),
        )
        return [
            ForeignKeyInfo(
                owner_table=row[4],
                column=row[2],
                referenced_table=table,
                referenced_column=row[5],
                owner_schema=row[3] or "",
                referenced_schema=schema,
                constraint_name=row[0],
                ordinal=int(row[1]),
            )
            for row in cursor.fetchall()
        ]

    def quote_identifier(self, name: str) -> str:
        """Quote an identifier for Redshift."""
        return f'"{name}"'

    def build_select_query(
        self, table: str, limit: int, database: str | None = None, schema: str | None = None
    ) -> str:
        """Build SELECT query with LIMIT."""
        schema = schema or self.default_schema
        return f'SELECT * FROM "{schema}"."{table}" LIMIT {limit}'
