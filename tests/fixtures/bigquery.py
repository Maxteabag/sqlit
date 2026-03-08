"""BigQuery fixtures (using bigquery-emulator)."""

from __future__ import annotations

import os
import time

import pytest

from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

BIGQUERY_HOST = os.environ.get("BIGQUERY_HOST", "localhost")
BIGQUERY_PORT = int(os.environ.get("BIGQUERY_PORT", "9050"))
BIGQUERY_PROJECT = os.environ.get("BIGQUERY_PROJECT", "test-project")
BIGQUERY_DATASET = os.environ.get("BIGQUERY_DATASET", "test_sqlit")
BIGQUERY_LOCATION = os.environ.get("BIGQUERY_LOCATION", "US")
BIGQUERY_EMULATOR_HOST = os.environ.get(
    "BIGQUERY_EMULATOR_HOST", f"http://{BIGQUERY_HOST}:{BIGQUERY_PORT}"
)

os.environ.setdefault("BIGQUERY_EMULATOR_HOST", BIGQUERY_EMULATOR_HOST)
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", BIGQUERY_PROJECT)


def bigquery_available() -> bool:
    """Check if BigQuery emulator is available."""
    return is_port_open(BIGQUERY_HOST, BIGQUERY_PORT)


@pytest.fixture(scope="session")
def bigquery_server_ready() -> bool:
    """Check if BigQuery emulator is ready and return True/False."""
    if not bigquery_available():
        return False

    time.sleep(1)
    return True


def _build_client():
    from google.api_core.client_options import ClientOptions
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import bigquery

    client_options = ClientOptions(api_endpoint=BIGQUERY_EMULATOR_HOST)
    return bigquery.Client(
        project=BIGQUERY_PROJECT,
        credentials=AnonymousCredentials(),
        client_options=client_options,
        location=BIGQUERY_LOCATION,
    )


def _table_exists(client, table_id: str) -> bool:
    """Check if a table exists in BigQuery."""
    from google.api_core.exceptions import NotFound

    try:
        client.get_table(table_id)
        return True
    except NotFound:
        return False


@pytest.fixture(scope="function")
def bigquery_db(bigquery_server_ready: bool) -> str:
    """Set up BigQuery dataset and tables.

    Note: The BigQuery emulator has several quirks:
    - Returns 500 instead of 409 for "already exists" errors
    - Returns 500 for delete operations on tables
    - The Google client retries 500 errors indefinitely

    To work around these issues, we:
    - Check if resources exist before creating them
    - Skip delete operations entirely (emulator resets on restart)
    """
    if not bigquery_server_ready:
        pytest.skip("BigQuery emulator is not available")

    try:
        from google.cloud import bigquery  # noqa: F401
    except ImportError:
        pytest.skip("google-cloud-bigquery is not installed")

    try:
        from google.api_core.exceptions import NotFound

        client = _build_client()

        dataset_id = f"{BIGQUERY_PROJECT}.{BIGQUERY_DATASET}"
        # Check if dataset exists before trying to create it
        # (emulator returns 500 instead of 409 for "already exists")
        try:
            client.get_dataset(dataset_id)
        except NotFound:
            dataset_ref = bigquery.Dataset(dataset_id)
            dataset_ref.location = BIGQUERY_LOCATION
            client.create_dataset(dataset_ref)

        users_schema = [
            bigquery.SchemaField("id", "INT64"),
            bigquery.SchemaField("name", "STRING"),
            bigquery.SchemaField("email", "STRING"),
        ]
        products_schema = [
            bigquery.SchemaField("id", "INT64"),
            bigquery.SchemaField("name", "STRING"),
            bigquery.SchemaField("price", "FLOAT"),
            bigquery.SchemaField("stock", "INT64"),
        ]

        users_table_id = f"{BIGQUERY_PROJECT}.{BIGQUERY_DATASET}.test_users"
        products_table_id = f"{BIGQUERY_PROJECT}.{BIGQUERY_DATASET}.test_products"
        view_id = f"{BIGQUERY_PROJECT}.{BIGQUERY_DATASET}.test_user_emails"

        # Create tables only if they don't exist
        # (emulator doesn't support delete, so we can't clean up)
        if not _table_exists(client, users_table_id):
            users_table = bigquery.Table(users_table_id, schema=users_schema)
            client.create_table(users_table)
            # Only insert data into newly created tables
            client.insert_rows_json(
                users_table,
                [
                    {"id": 1, "name": "Alice", "email": "alice@example.com"},
                    {"id": 2, "name": "Bob", "email": "bob@example.com"},
                    {"id": 3, "name": "Charlie", "email": "charlie@example.com"},
                ],
            )

        if not _table_exists(client, products_table_id):
            products_table = bigquery.Table(products_table_id, schema=products_schema)
            client.create_table(products_table)
            client.insert_rows_json(
                products_table,
                [
                    {"id": 1, "name": "Widget", "price": 9.99, "stock": 100},
                    {"id": 2, "name": "Gadget", "price": 19.99, "stock": 50},
                    {"id": 3, "name": "Gizmo", "price": 29.99, "stock": 25},
                ],
            )

        if not _table_exists(client, view_id):
            view = bigquery.Table(view_id)
            view.view_query = (
                f"SELECT id, name, email FROM `{BIGQUERY_PROJECT}.{BIGQUERY_DATASET}.test_users` "
                "WHERE email != ''"
            )
            client.create_table(view)

    except Exception as exc:
        pytest.skip(f"Failed to setup BigQuery dataset: {exc}")

    yield BIGQUERY_DATASET

    # Skip cleanup - emulator doesn't support delete operations properly
    # (returns 500 errors that cause infinite retries)


@pytest.fixture(scope="function")
def bigquery_connection(bigquery_db: str) -> str:
    """Create a sqlit CLI connection for BigQuery and clean up after test."""
    connection_name = f"test_bigquery_{os.getpid()}"

    cleanup_connection(connection_name)

    args = [
        "connections",
        "add",
        "bigquery",
        "--name",
        connection_name,
        "--server",
        BIGQUERY_PROJECT,
        "--database",
        bigquery_db,
        "--bigquery-location",
        BIGQUERY_LOCATION,
    ]

    run_cli(*args)

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "BIGQUERY_DATASET",
    "BIGQUERY_EMULATOR_HOST",
    "BIGQUERY_HOST",
    "BIGQUERY_LOCATION",
    "BIGQUERY_PORT",
    "BIGQUERY_PROJECT",
    "bigquery_available",
    "bigquery_connection",
    "bigquery_db",
    "bigquery_server_ready",
]
