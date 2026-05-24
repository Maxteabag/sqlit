"""Google Cloud Spanner fixtures (using spanner-emulator)."""

from __future__ import annotations

import os
import time

import pytest

from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

SPANNER_HOST = os.environ.get("SPANNER_HOST", "localhost")
SPANNER_PORT = int(os.environ.get("SPANNER_PORT", "9010"))
SPANNER_PROJECT = os.environ.get("SPANNER_PROJECT", "test-project")
SPANNER_INSTANCE = os.environ.get("SPANNER_INSTANCE", "test-instance")
SPANNER_DATABASE = os.environ.get("SPANNER_DATABASE", "test-database")
SPANNER_EMULATOR_HOST = os.environ.get(
    "SPANNER_EMULATOR_HOST", f"{SPANNER_HOST}:{SPANNER_PORT}"
)

os.environ.setdefault("SPANNER_EMULATOR_HOST", SPANNER_EMULATOR_HOST)


def spanner_available() -> bool:
    """Check if Spanner emulator is available."""
    return is_port_open(SPANNER_HOST, SPANNER_PORT)


@pytest.fixture(scope="session")
def spanner_server_ready() -> bool:
    """Check if Spanner emulator is ready and return True/False."""
    if not spanner_available():
        return False

    time.sleep(1)
    return True


def _create_instance_and_database():
    """Create instance and database in emulator using the admin client."""
    from google.cloud import spanner

    client = spanner.Client(project=SPANNER_PROJECT)

    # Create instance
    instance = client.instance(SPANNER_INSTANCE)
    if not instance.exists():
        config_name = f"projects/{SPANNER_PROJECT}/instanceConfigs/emulator-config"
        operation = instance.create(
            display_name="Test Instance",
            configuration_name=config_name,
            node_count=1,
        )
        operation.result()

    # Create database
    database = instance.database(SPANNER_DATABASE)
    if not database.exists():
        operation = database.create()
        operation.result()

    return database


def _table_exists(database, table_name: str) -> bool:
    """Check if a table exists in Spanner."""
    with database.snapshot() as snapshot:
        results = snapshot.execute_sql(
            """
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME = @table_name
            """,
            params={"table_name": table_name},
            param_types={"table_name": "STRING"},
        )
        return len(list(results)) > 0


@pytest.fixture(scope="function")
def spanner_db(spanner_server_ready: bool) -> str:
    """Set up Spanner database and tables."""
    if not spanner_server_ready:
        pytest.skip("Spanner emulator is not available")

    try:
        from google.cloud import spanner  # noqa: F401
    except ImportError:
        pytest.skip("google-cloud-spanner is not installed")

    try:
        database = _create_instance_and_database()

        # Create tables using DDL
        ddl_statements = []

        if not _table_exists(database, "test_users"):
            ddl_statements.append("""
                CREATE TABLE test_users (
                    id INT64 NOT NULL,
                    name STRING(100),
                    email STRING(100)
                ) PRIMARY KEY (id)
            """)

        if not _table_exists(database, "test_products"):
            ddl_statements.append("""
                CREATE TABLE test_products (
                    id INT64 NOT NULL,
                    name STRING(100),
                    price FLOAT64,
                    stock INT64
                ) PRIMARY KEY (id)
            """)

        if ddl_statements:
            operation = database.update_ddl(ddl_statements)
            operation.result()

        # Insert test data using mutations
        with database.batch() as batch:
            # Check if data exists first
            with database.snapshot() as snapshot:
                results = snapshot.execute_sql("SELECT COUNT(*) FROM test_users")
                count = next(iter(results))[0]
                if count == 0:
                    batch.insert(
                        "test_users",
                        columns=["id", "name", "email"],
                        values=[
                            (1, "Alice", "alice@example.com"),
                            (2, "Bob", "bob@example.com"),
                            (3, "Charlie", "charlie@example.com"),
                        ],
                    )

            with database.snapshot() as snapshot:
                results = snapshot.execute_sql("SELECT COUNT(*) FROM test_products")
                count = next(iter(results))[0]
                if count == 0:
                    batch.insert(
                        "test_products",
                        columns=["id", "name", "price", "stock"],
                        values=[
                            (1, "Widget", 9.99, 100),
                            (2, "Gadget", 19.99, 50),
                            (3, "Gizmo", 29.99, 25),
                        ],
                    )

        # Create view (if not exists) - Spanner uses INFORMATION_SCHEMA for views
        try:
            if not _table_exists(database, "test_user_emails"):
                operation = database.update_ddl(["""
                    CREATE VIEW test_user_emails SQL SECURITY INVOKER AS
                    SELECT id, name, email FROM test_users
                """])
                operation.result()
        except Exception:
            # Views might not be fully supported in emulator, skip silently
            pass

        # Create index
        try:
            with database.snapshot() as snapshot:
                results = snapshot.execute_sql("""
                    SELECT INDEX_NAME FROM INFORMATION_SCHEMA.INDEXES
                    WHERE INDEX_NAME = 'idx_test_users_email'
                """)
                if len(list(results)) == 0:
                    operation = database.update_ddl([
                        "CREATE INDEX idx_test_users_email ON test_users(email)"
                    ])
                    operation.result()
        except Exception:
            pass  # Index might already exist

    except Exception as exc:
        pytest.skip(f"Failed to setup Spanner database: {exc}")

    yield SPANNER_DATABASE


@pytest.fixture(scope="function")
def spanner_connection(spanner_db: str) -> str:
    """Create a sqlit CLI connection for Spanner and clean up after test."""
    connection_name = f"test_spanner_{os.getpid()}"

    cleanup_connection(connection_name)

    args = [
        "connections",
        "add",
        "spanner",
        "--name",
        connection_name,
        "--spanner-project",
        SPANNER_PROJECT,
        "--spanner-instance",
        SPANNER_INSTANCE,
        "--database",
        spanner_db,
        "--spanner-emulator-host",
        SPANNER_EMULATOR_HOST,
    ]

    run_cli(*args)

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "SPANNER_DATABASE",
    "SPANNER_EMULATOR_HOST",
    "SPANNER_HOST",
    "SPANNER_INSTANCE",
    "SPANNER_PORT",
    "SPANNER_PROJECT",
    "spanner_available",
    "spanner_connection",
    "spanner_db",
    "spanner_server_ready",
]
