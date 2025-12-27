"""AWS Athena adapter using pyathena."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import CursorBasedAdapter, import_driver_module, ColumnInfo, IndexInfo, TriggerInfo, SequenceInfo, TableInfo

if TYPE_CHECKING:
    from ...config import ConnectionConfig


class AthenaAdapter(CursorBasedAdapter):
    """Adapter for AWS Athena."""

    @classmethod
    def badge_label(cls) -> str:
        return "Athena"

    @property
    def name(self) -> str:
        return "Athena"

    @property
    def install_extra(self) -> str:
        return "athena"

    @property
    def install_package(self) -> str:
        return "pyathena"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("pyathena",)

    @property
    def supports_multiple_databases(self) -> bool:
        return True

    @property
    def supports_stored_procedures(self) -> bool:
        return False

    @property
    def supports_triggers(self) -> bool:
        return False

    @property
    def supports_indexes(self) -> bool:
        return False

    @property
    def supports_cross_database_queries(self) -> bool:
        """Athena supports cross-database queries using database.table syntax."""
        return True

    @property
    def system_databases(self) -> frozenset[str]:
        """Athena system databases to exclude from user listings."""
        return frozenset({"information_schema"})

    @property
    def default_schema(self) -> str:
        return "default"

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to AWS Athena."""
        pyathena = import_driver_module(
            "pyathena",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        auth_method = config.options.get("athena_auth_method", "profile")

        connect_args = {
            "region_name": config.options.get("athena_region_name", "us-east-1"),
            "s3_staging_dir": config.options.get("athena_s3_staging_dir"),
            "schema_name": config.database or "default",
        }

        if auth_method == "keys":
            connect_args["aws_access_key_id"] = config.username
            connect_args["aws_secret_access_key"] = config.password
        else:
            connect_args["profile_name"] = config.options.get("athena_profile_name", "default")

        # Optional WorkGroup
        if "athena_work_group" in config.options:
            connect_args["work_group"] = config.options["athena_work_group"]

        return pyathena.connect(**connect_args)

    def get_databases(self, conn: Any) -> list[str]:
        """Get list of databases (schemas in Athena)."""
        cursor = conn.cursor()
        cursor.execute("SHOW DATABASES")
        return [row[0] for row in cursor.fetchall()]

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables."""
        cursor = conn.cursor()
        if database:
            cursor.execute(f"SHOW TABLES IN {database}")
        else:
            cursor.execute("SHOW TABLES")
        return [(database or self.default_schema, row[0]) for row in cursor.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of views."""
        cursor = conn.cursor()
        if database:
            cursor.execute(f"SHOW VIEWS IN {database}")
        else:
            cursor.execute("SHOW VIEWS")
        return [(database or self.default_schema, row[0]) for row in cursor.fetchall()]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get columns for a table or view."""
        cursor = conn.cursor()

        target_db = database or schema or self.default_schema
        full_table = f"{target_db}.{table}"
        cursor.execute(f"DESCRIBE {full_table}")

        columns = []
        rows = cursor.fetchall()
        for row in rows:
            # A table row element looks like this: ('col_name            \tstring              \tfrom deserializer   ',)
            # A view row element looks like this: ('col_name            \tstring   ',)
            col_name, data_type = [e.strip() for e in row[0].split("\t")[:2]]
            columns.append(ColumnInfo(name=col_name, data_type=data_type, is_primary_key=False))

        return columns

    def quote_identifier(self, name: str) -> str:
        return name

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        """Build SELECT LIMIT query."""
        target_db = database or schema or self.default_schema
        return f"SELECT * FROM {target_db}.{table} LIMIT {limit}"

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        return []

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        return []

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        return []

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        return []
