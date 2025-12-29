"""Google BigQuery adapter using sqlalchemy-bigquery."""

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


class BigQueryAdapter(CursorBasedAdapter):
    """Adapter for Google BigQuery."""

    @classmethod
    def badge_label(cls) -> str:
        return "BQ"

    @classmethod
    def url_schemes(cls) -> tuple[str, ...]:
        return ("bigquery",)

    @property
    def name(self) -> str:
        return "BigQuery"

    @property
    def install_extra(self) -> str:
        return "bigquery"

    @property
    def install_package(self) -> str:
        return "sqlalchemy-bigquery"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("sqlalchemy_bigquery",)

    @property
    def supports_multiple_databases(self) -> bool:
        # BigQuery uses datasets as the equivalent of databases
        return True

    @property
    def supports_stored_procedures(self) -> bool:
        return True

    @property
    def supports_triggers(self) -> bool:
        return False

    @property
    def supports_indexes(self) -> bool:
        return False

    @property
    def supports_cross_database_queries(self) -> bool:
        # BigQuery supports cross-dataset queries
        return True

    @property
    def system_databases(self) -> frozenset[str]:
        return frozenset({"INFORMATION_SCHEMA"})

    @property
    def default_schema(self) -> str:
        return "default"

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to Google BigQuery."""
        # Import sqlalchemy for creating engine
        sqlalchemy = import_driver_module(
            "sqlalchemy",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        # Ensure sqlalchemy-bigquery is available
        import_driver_module(
            "sqlalchemy_bigquery",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        project_id = config.server or config.options.get("bigquery_project")
        location = config.options.get("bigquery_location", "US")

        # Build connection URL
        url = f"bigquery://{project_id}" if project_id else "bigquery://"

        connect_args: dict[str, Any] = {
            "location": location,
        }

        # Handle authentication
        auth_method = config.options.get("bigquery_auth_method", "default")

        if auth_method == "service_account" and config.options.get("bigquery_credentials_path"):
            connect_args["credentials_path"] = config.options["bigquery_credentials_path"]

        # Create SQLAlchemy engine
        engine = sqlalchemy.create_engine(url, **connect_args)

        # Return a connection from the engine
        return engine.connect()

    def get_databases(self, conn: Any) -> list[str]:
        """Get list of datasets from BigQuery."""
        result = conn.execute(
            "SELECT schema_name FROM INFORMATION_SCHEMA.SCHEMATA ORDER BY schema_name"
        )
        return [row[0] for row in result.fetchall()]

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables."""
        if database:
            query = f"""
                SELECT table_schema, table_name
                FROM `{database}`.INFORMATION_SCHEMA.TABLES
                WHERE table_type = 'BASE TABLE'
                ORDER BY table_schema, table_name
            """
        else:
            query = """
                SELECT table_schema, table_name
                FROM INFORMATION_SCHEMA.TABLES
                WHERE table_type = 'BASE TABLE'
                ORDER BY table_schema, table_name
            """
        result = conn.execute(query)
        return [(row[0], row[1]) for row in result.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of views."""
        if database:
            query = f"""
                SELECT table_schema, table_name
                FROM `{database}`.INFORMATION_SCHEMA.TABLES
                WHERE table_type = 'VIEW'
                ORDER BY table_schema, table_name
            """
        else:
            query = """
                SELECT table_schema, table_name
                FROM INFORMATION_SCHEMA.TABLES
                WHERE table_type = 'VIEW'
                ORDER BY table_schema, table_name
            """
        result = conn.execute(query)
        return [(row[0], row[1]) for row in result.fetchall()]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get columns for a table."""
        dataset = database or schema or self.default_schema

        query = f"""
            SELECT column_name, data_type
            FROM `{dataset}`.INFORMATION_SCHEMA.COLUMNS
            WHERE table_name = @table_name
            ORDER BY ordinal_position
        """
        # BigQuery uses parameterized queries differently
        result = conn.execute(
            query.replace("@table_name", f"'{table}'")
        )

        return [
            ColumnInfo(name=row[0], data_type=row[1], is_primary_key=False)
            for row in result.fetchall()
        ]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """Get routines from BigQuery."""
        if database:
            query = f"""
                SELECT routine_name
                FROM `{database}`.INFORMATION_SCHEMA.ROUTINES
                ORDER BY routine_name
            """
        else:
            query = """
                SELECT routine_name
                FROM INFORMATION_SCHEMA.ROUTINES
                ORDER BY routine_name
            """
        try:
            result = conn.execute(query)
            return [row[0] for row in result.fetchall()]
        except Exception:
            return []

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        """BigQuery doesn't have traditional indexes."""
        return []

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        """BigQuery doesn't support triggers."""
        return []

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        """BigQuery doesn't support sequences."""
        return []

    def quote_identifier(self, name: str) -> str:
        """Quote an identifier for BigQuery."""
        return f"`{name}`"

    def build_select_query(
        self, table: str, limit: int, database: str | None = None, schema: str | None = None
    ) -> str:
        """Build SELECT query with LIMIT."""
        dataset = database or schema or self.default_schema
        return f"SELECT * FROM `{dataset}`.`{table}` LIMIT {limit}"
