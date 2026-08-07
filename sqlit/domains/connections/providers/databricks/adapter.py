"""Databricks adapter using databricks-sql-connector.

Databricks SQL uses a three-level namespace via Unity Catalog:
    catalog.schema.table

We map Databricks' "catalog" to the generic `database` slot in
sqlit's connection model, mirroring how Trino is handled.
"""

from __future__ import annotations

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


class DatabricksAdapter(CursorBasedAdapter):
    """Adapter for Databricks SQL warehouses and clusters."""

    @property
    def name(self) -> str:
        return "Databricks"

    @property
    def install_extra(self) -> str:
        return "databricks"

    @property
    def install_package(self) -> str:
        return "databricks-sql-connector"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("databricks.sql",)

    @property
    def supports_multiple_databases(self) -> bool:
        return True

    @property
    def supports_cross_database_queries(self) -> bool:
        return True

    @property
    def supports_stored_procedures(self) -> bool:
        return False

    @property
    def supports_indexes(self) -> bool:
        return False

    @property
    def supports_triggers(self) -> bool:
        return False

    @property
    def supports_sequences(self) -> bool:
        return False

    @property
    def default_schema(self) -> str:
        return "default"

    @property
    def system_databases(self) -> frozenset[str]:
        # Built-in Databricks catalogs we usually want to hide from the
        # primary picker. `samples` is the public demo catalog and
        # `system` holds Unity Catalog telemetry.
        return frozenset({"system"})

    def apply_database_override(self, config: ConnectionConfig, database: str) -> ConnectionConfig:
        """Apply a default catalog for unqualified queries."""
        if not database:
            return config
        return config.with_endpoint(database=database)

    def connect(self, config: ConnectionConfig) -> Any:
        sql_module = self._import_driver_module(
            "databricks.sql",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        endpoint = config.tcp_endpoint
        if endpoint is None:
            raise ValueError("Databricks connections require a TCP-style endpoint.")

        extras = config.options
        http_path = extras.get("http_path") or config.extra_options.get("http_path")
        if not http_path:
            raise ValueError("Databricks requires an HTTP Path (SQL warehouse or cluster).")

        connect_args: dict[str, Any] = {
            "server_hostname": endpoint.host,
            "http_path": http_path,
        }

        catalog = endpoint.database
        if catalog:
            connect_args["catalog"] = catalog
        schema = extras.get("schema")
        if schema:
            connect_args["schema"] = schema

        auth_type = extras.get("auth_type", "pat")
        if auth_type == "pat":
            token = extras.get("access_token") or endpoint.password
            if not token:
                raise ValueError("Databricks PAT authentication requires an access token.")
            connect_args["access_token"] = token
        elif auth_type == "oauth-u2m":
            connect_args["auth_type"] = "databricks-oauth"
        elif auth_type == "oauth-m2m":
            client_id = extras.get("client_id")
            client_secret = extras.get("client_secret")
            if not client_id or not client_secret:
                raise ValueError(
                    "Databricks OAuth (Service Principal) requires client_id and client_secret."
                )
            connect_args["credentials_provider"] = _build_m2m_credentials_provider(
                endpoint.host, client_id, client_secret
            )
        else:
            raise ValueError(f"Unknown Databricks auth_type: {auth_type}")

        connect_args.update(config.extra_options)
        # http_path may have been passed via extra_options; drop the legacy key
        # so it isn't sent twice if both schemes were used.
        connect_args.pop("http_path", None)
        connect_args["http_path"] = http_path

        return sql_module.connect(**connect_args)

    def get_databases(self, conn: Any) -> list[str]:
        """List Unity Catalog catalogs."""
        cursor = conn.cursor()
        # SHOW CATALOGS is universally supported and avoids needing
        # SELECT privilege on system.information_schema.
        cursor.execute("SHOW CATALOGS")
        return [row[0] for row in cursor.fetchall()]

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT table_schema, table_name FROM "
                f"{self.quote_identifier(database)}.information_schema.tables "
                "WHERE table_type IN ('MANAGED', 'EXTERNAL', 'BASE TABLE') "
                "ORDER BY table_schema, table_name"
            )
            return [(row[0], row[1]) for row in cursor.fetchall()]

        cursor.execute("SHOW TABLES")
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT table_schema, table_name FROM "
                f"{self.quote_identifier(database)}.information_schema.views "
                "ORDER BY table_schema, table_name"
            )
            return [(row[0], row[1]) for row in cursor.fetchall()]

        cursor.execute("SHOW VIEWS")
        # SHOW VIEWS columns: database, viewName, isTemporary
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        cursor = conn.cursor()
        schema_name = schema or self.default_schema
        if database:
            cursor.execute(
                "SELECT column_name, data_type FROM "
                f"{self.quote_identifier(database)}.information_schema.columns "
                "WHERE table_schema = ? AND table_name = ? "
                "ORDER BY ordinal_position",
                (schema_name, table),
            )
        else:
            cursor.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = ? AND table_name = ? "
                "ORDER BY ordinal_position",
                (schema_name, table),
            )
        return [ColumnInfo(name=row[0], data_type=row[1]) for row in cursor.fetchall()]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        return []

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        return []

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        return []

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        return []

    def quote_identifier(self, name: str) -> str:
        """Quote identifier using backticks (Databricks/Spark SQL standard)."""
        escaped = name.replace("`", "``")
        return f"`{escaped}`"

    def build_select_query(
        self, table: str, limit: int, database: str | None = None, schema: str | None = None
    ) -> str:
        schema_name = schema or self.default_schema
        if database and schema_name:
            return (
                f"SELECT * FROM {self.quote_identifier(database)}."
                f"{self.quote_identifier(schema_name)}."
                f"{self.quote_identifier(table)} LIMIT {limit}"
            )
        if schema_name:
            return f"SELECT * FROM {self.quote_identifier(schema_name)}.{self.quote_identifier(table)} LIMIT {limit}"
        return f"SELECT * FROM {self.quote_identifier(table)} LIMIT {limit}"


def _build_m2m_credentials_provider(host: str, client_id: str, client_secret: str) -> Any:
    """Return a credentials_provider callable for Databricks OAuth M2M.

    Imported lazily so the databricks-sdk dependency is only required
    when the user actually selects service-principal auth.
    """

    def _factory() -> Any:
        from databricks.sdk.core import Config, oauth_service_principal

        cfg = Config(
            host=host if host.startswith(("http://", "https://")) else f"https://{host}",
            client_id=client_id,
            client_secret=client_secret,
        )
        return oauth_service_principal(cfg)

    return _factory
