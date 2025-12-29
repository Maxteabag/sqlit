"""Amazon Redshift adapter using redshift_connector."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import (
    ColumnInfo,
    CursorBasedAdapter,
    IndexInfo,
    SequenceInfo,
    TableInfo,
    TriggerInfo,
    import_driver_module,
)

if TYPE_CHECKING:
    from ...config import ConnectionConfig


class RedshiftAdapter(CursorBasedAdapter):
    """Adapter for Amazon Redshift."""

    @classmethod
    def badge_label(cls) -> str:
        return "RS"

    @classmethod
    def url_schemes(cls) -> tuple[str, ...]:
        return ("redshift",)

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
    def supports_cross_database_queries(self) -> bool:
        return True

    @property
    def system_databases(self) -> frozenset[str]:
        return frozenset({"template0", "template1", "padb_harvest"})

    @property
    def default_schema(self) -> str:
        return "public"

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to Amazon Redshift."""
        redshift_connector = import_driver_module(
            "redshift_connector",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        auth_method = config.options.get("redshift_auth_method", "password")

        connect_args: dict[str, Any] = {
            "host": config.server,
            "port": int(config.port or "5439"),
            "database": config.database or "dev",
        }

        if auth_method == "iam":
            # IAM authentication
            connect_args["iam"] = True
            connect_args["db_user"] = config.username
            connect_args["cluster_identifier"] = config.options.get("redshift_cluster_id")
            connect_args["region"] = config.options.get("redshift_region", "us-east-1")
            if config.options.get("redshift_profile"):
                connect_args["profile"] = config.options["redshift_profile"]
        else:
            # Standard password authentication
            connect_args["user"] = config.username
            connect_args["password"] = config.password

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

    def quote_identifier(self, name: str) -> str:
        """Quote an identifier for Redshift."""
        return f'"{name}"'

    def build_select_query(
        self, table: str, limit: int, database: str | None = None, schema: str | None = None
    ) -> str:
        """Build SELECT query with LIMIT."""
        schema = schema or self.default_schema
        return f'SELECT * FROM "{schema}"."{table}" LIMIT {limit}'
