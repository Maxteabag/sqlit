"""Google BigQuery adapter using google-cloud-bigquery DB-API."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Iterable

from sqlit.domains.connections.providers.adapters.base import (
    ColumnInfo,
    CursorBasedAdapter,
    IndexInfo,
    SequenceInfo,
    TableInfo,
    TriggerInfo,
)

if TYPE_CHECKING:
    from google.cloud import bigquery
    from google.cloud.bigquery.dbapi import Connection as BigQueryConnection
    from sqlit.domains.connections.domain.config import ConnectionConfig


class BigQueryAdapter(CursorBasedAdapter):
    """Adapter for Google BigQuery."""

    @property
    def name(self) -> str:
        return "BigQuery"

    @property
    def install_extra(self) -> str:
        return "bigquery"

    @property
    def install_package(self) -> str:
        return "google-cloud-bigquery"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("google.cloud.bigquery", "google.cloud.bigquery.dbapi")

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

    def apply_database_override(self, config: ConnectionConfig, database: str) -> ConnectionConfig:
        """Apply a default dataset for unqualified queries."""
        if not database:
            return config
        return config.with_endpoint(database=database)

    @property
    def system_databases(self) -> frozenset[str]:
        return frozenset({"INFORMATION_SCHEMA"})

    @property
    def default_schema(self) -> str:
        return ""

    def _resolve_project_id(self, config: ConnectionConfig) -> str:
        endpoint = config.tcp_endpoint
        project_id = (endpoint.host if endpoint else "") or config.options.get("bigquery_project", "")
        if project_id:
            return project_id
        return os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT") or ""

    def _resolve_default_dataset(self, config: ConnectionConfig) -> str | None:
        endpoint = config.tcp_endpoint
        if endpoint and endpoint.database:
            return endpoint.database
        dataset = config.options.get("bigquery_dataset")
        return dataset if isinstance(dataset, str) and dataset else None

    def _get_connection_job_config(self, conn: Any) -> Any | None:
        return getattr(conn, "_sqlit_bq_job_config", None)

    def _get_default_dataset_for_conn(self, conn: Any) -> str | None:
        dataset = getattr(conn, "_sqlit_bq_default_dataset", None)
        if isinstance(dataset, str) and dataset:
            return dataset
        return None

    def _get_client(self, conn: Any) -> bigquery.Client | None:
        client = getattr(conn, "client", None)
        if client is not None:
            return client
        client = getattr(conn, "_sqlit_bq_client", None)
        return client

    def connect(self, config: ConnectionConfig) -> BigQueryConnection:
        """Connect to Google BigQuery using the DB-API connector."""
        bigquery = self._import_driver_module(
            "google.cloud.bigquery",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )
        dbapi = self._import_driver_module(
            "google.cloud.bigquery.dbapi",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        project_id = self._resolve_project_id(config)
        location = config.options.get("bigquery_location", "US")
        default_dataset = self._resolve_default_dataset(config)

        credentials = None
        client_options = None

        # Check for emulator: either via env var or by detecting a port in config
        # (BigQuery doesn't normally use TCP, so any port means emulator)
        emulator_host = os.environ.get("BIGQUERY_EMULATOR_HOST")
        endpoint = config.tcp_endpoint
        if not emulator_host and endpoint and endpoint.port:
            # Any port specified means we're connecting to an emulator
            # Default to localhost if no explicit host for emulator
            host = "localhost"
            emulator_host = f"http://{host}:{endpoint.port}"

        if emulator_host:
            if not emulator_host.startswith("http"):
                emulator_host = f"http://{emulator_host}"
            from google.api_core.client_options import ClientOptions
            from google.auth.credentials import AnonymousCredentials

            client_options = ClientOptions(api_endpoint=emulator_host)
            credentials = AnonymousCredentials()
        else:
            auth_method = config.options.get("bigquery_auth_method", "default")
            if auth_method == "service_account":
                credentials_path = config.options.get("bigquery_credentials_path")
                if credentials_path:
                    from google.oauth2 import service_account

                    credentials = service_account.Credentials.from_service_account_file(credentials_path)

        client_kwargs: dict[str, Any] = {}
        if project_id:
            client_kwargs["project"] = project_id
        if location:
            client_kwargs["location"] = location
        if credentials:
            client_kwargs["credentials"] = credentials
        if client_options:
            client_kwargs["client_options"] = client_options

        client = bigquery.Client(**client_kwargs)

        job_config = None
        if default_dataset:
            if "." in default_dataset:
                dataset_project, dataset_id = default_dataset.split(".", 1)
                dataset_ref = bigquery.DatasetReference(dataset_project, dataset_id)
            elif client.project:
                dataset_ref = bigquery.DatasetReference(client.project, default_dataset)
            else:
                dataset_ref = None
            if dataset_ref is not None:
                job_config = bigquery.QueryJobConfig(default_dataset=dataset_ref)
                client.default_query_job_config = job_config

        conn = dbapi.connect(client=client)
        setattr(conn, "_sqlit_bq_client", client)
        if default_dataset:
            setattr(conn, "_sqlit_bq_default_dataset", default_dataset)
        if job_config:
            setattr(conn, "_sqlit_bq_job_config", job_config)

        return conn

    def execute_query(self, conn: Any, query: str, max_rows: int | None = None) -> tuple[list[str], list[tuple], bool]:
        """Execute a query with optional default dataset configuration."""
        cursor = conn.cursor()
        job_config = self._get_connection_job_config(conn)
        if job_config is not None:
            cursor.execute(query, job_config=job_config)
        else:
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
        """Execute a non-query statement for BigQuery."""
        cursor = conn.cursor()
        job_config = self._get_connection_job_config(conn)
        if job_config is not None:
            cursor.execute(query, job_config=job_config)
        else:
            cursor.execute(query)

        rowcount = int(getattr(cursor, "rowcount", -1) or -1)
        commit = getattr(conn, "commit", None)
        if callable(commit):
            try:
                commit()
            except Exception:
                pass
        return rowcount

    def _resolve_dataset(self, conn: Any, database: str | None, schema: str | None) -> str | None:
        if database:
            return database
        if schema:
            return schema
        return self._get_default_dataset_for_conn(conn)

    def _iter_datasets(self, client: bigquery.Client) -> Iterable[str]:
        for dataset in client.list_datasets(project=client.project):
            dataset_id = getattr(dataset, "dataset_id", None)
            if isinstance(dataset_id, str) and dataset_id:
                yield dataset_id

    def _list_tables_for_dataset(
        self,
        client: bigquery.Client,
        dataset_id: str,
        table_types: set[str],
    ) -> list[TableInfo]:
        dataset_ref = dataset_id
        if "." not in dataset_id and client.project:
            dataset_ref = f"{client.project}.{dataset_id}"
        tables: list[TableInfo] = []
        for table in client.list_tables(dataset_ref):
            table_type = getattr(table, "table_type", "")
            if table_type in table_types:
                tables.append((dataset_id, table.table_id))
        return tables

    def get_databases(self, conn: Any) -> list[str]:
        """Get list of datasets from BigQuery."""
        client = self._get_client(conn)
        if client is None:
            return []
        return list(self._iter_datasets(client))

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables."""
        client = self._get_client(conn)
        if client is None:
            return []

        dataset = self._resolve_dataset(conn, database, None)
        table_types = {"TABLE"}

        if dataset:
            return self._list_tables_for_dataset(client, dataset, table_types)

        tables: list[TableInfo] = []
        for dataset_id in self._iter_datasets(client):
            tables.extend(self._list_tables_for_dataset(client, dataset_id, table_types))
        return tables

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of views."""
        client = self._get_client(conn)
        if client is None:
            return []

        dataset = self._resolve_dataset(conn, database, None)
        table_types = {"VIEW", "MATERIALIZED_VIEW"}

        if dataset:
            return self._list_tables_for_dataset(client, dataset, table_types)

        views: list[TableInfo] = []
        for dataset_id in self._iter_datasets(client):
            views.extend(self._list_tables_for_dataset(client, dataset_id, table_types))
        return views

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get columns for a table."""
        client = self._get_client(conn)
        if client is None:
            return []

        dataset = self._resolve_dataset(conn, database, schema)
        if not dataset:
            return []

        if "." in dataset or not client.project:
            table_ref = f"{dataset}.{table}"
        else:
            table_ref = f"{client.project}.{dataset}.{table}"
        table_obj = client.get_table(table_ref)
        return [
            ColumnInfo(name=field.name, data_type=field.field_type, is_primary_key=False)
            for field in table_obj.schema
        ]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """Get routines from BigQuery."""
        client = self._get_client(conn)
        if client is None:
            return []

        dataset = self._resolve_dataset(conn, database, None)
        if not dataset:
            return []

        list_routines = getattr(client, "list_routines", None)
        if not callable(list_routines):
            return []

        routine_dataset = dataset
        if "." not in dataset and client.project:
            routine_dataset = f"{client.project}.{dataset}"
        routines = list_routines(routine_dataset)
        names: list[str] = []
        for routine in routines:
            routine_id = getattr(routine, "routine_id", None)
            if routine_id:
                names.append(routine_id)
                continue
            reference = getattr(routine, "reference", None)
            if reference and getattr(reference, "routine_id", None):
                names.append(reference.routine_id)
        return names

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
        dataset = database or schema
        if dataset:
            if "." in dataset:
                return f"SELECT * FROM `{dataset}.{table}` LIMIT {limit}"
            return f"SELECT * FROM `{dataset}`.`{table}` LIMIT {limit}"
        return f"SELECT * FROM `{table}` LIMIT {limit}"
