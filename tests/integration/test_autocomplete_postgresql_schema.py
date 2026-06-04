"""Integration tests for PostgreSQL schema-qualified autocomplete."""

from __future__ import annotations

import os
import tempfile

import pytest

from sqlit.domains.shell.app.main import SSMSTUI
from tests.fixtures.postgres import (
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
)
from tests.helpers import ConnectionConfig
from tests.integration.browsing_base import wait_for_condition


@pytest.fixture
def temp_config_dir():
    """Create a temporary config directory for tests."""
    with tempfile.TemporaryDirectory(prefix="sqlit-test-") as tmpdir:
        original = os.environ.get("SQLIT_CONFIG_DIR")
        os.environ["SQLIT_CONFIG_DIR"] = tmpdir
        yield tmpdir
        if original:
            os.environ["SQLIT_CONFIG_DIR"] = original
        else:
            os.environ.pop("SQLIT_CONFIG_DIR", None)


@pytest.fixture
def postgres_schema_table(postgres_server_ready: bool, postgres_db: str):
    """Create a non-default schema table that requires schema qualification."""
    if not postgres_server_ready:
        pytest.skip("PostgreSQL is not available")

    try:
        import psycopg2
    except ImportError:
        pytest.skip("psycopg2 is not installed")

    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=postgres_db,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        connect_timeout=10,
    )
    conn.autocommit = True
    cursor = conn.cursor()
    cursor.execute("DROP SCHEMA IF EXISTS test CASCADE")
    cursor.execute("CREATE SCHEMA test")
    cursor.execute("""
        CREATE TABLE test.hello_world (
            id INTEGER PRIMARY KEY,
            greeting TEXT NOT NULL
        )
    """)
    cursor.execute("INSERT INTO test.hello_world (id, greeting) VALUES (1, 'hello')")
    conn.close()

    yield

    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=postgres_db,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        connect_timeout=10,
    )
    conn.autocommit = True
    cursor = conn.cursor()
    cursor.execute("DROP SCHEMA IF EXISTS test CASCADE")
    conn.close()


def _suggestions(app: SSMSTUI, sql: str) -> list[str]:
    return app._get_autocomplete_suggestions(sql, len(sql))


@pytest.mark.asyncio
async def test_postgresql_schema_table_autocomplete(
    postgres_server_ready: bool,
    postgres_db: str,
    postgres_schema_table,
    temp_config_dir: str,
) -> None:
    """Autocomplete should offer schema names and schema-local tables."""
    if not postgres_server_ready:
        pytest.skip("PostgreSQL is not available")

    config = ConnectionConfig(
        name="test-postgres-schema-autocomplete",
        db_type="postgresql",
        server=POSTGRES_HOST,
        port=str(POSTGRES_PORT),
        database=postgres_db,
        username=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )

    app = SSMSTUI()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)

        app.connections = [config]
        app.refresh_tree()
        await wait_for_condition(
            pilot,
            lambda: len(app.object_tree.root.children) > 0,
            timeout_seconds=5.0,
            description="tree to be populated with connections",
        )

        app.connect_to_server(config)
        await wait_for_condition(
            pilot,
            lambda: app.current_connection is not None,
            timeout_seconds=15.0,
            description="connection to be established",
        )

        load_schema_async = getattr(app, "_load_schema_cache_async", None)
        if callable(load_schema_async):
            await load_schema_async()

        await wait_for_condition(
            pilot,
            lambda: "test.hello_world" in getattr(app, "_table_metadata", {}),
            timeout_seconds=20.0,
            description="schema-qualified table metadata to be loaded",
        )

        from_schema_prefix = _suggestions(app, "SELECT * FROM tes")
        assert "test" in from_schema_prefix
        assert "hello_world" not in from_schema_prefix

        from_schema_dot = _suggestions(app, "SELECT * FROM test.")
        assert "hello_world" in from_schema_dot
        assert "Loading..." not in from_schema_dot

        alias_columns = _suggestions(app, "SELECT * FROM test.hello_world h WHERE h.")
        if alias_columns == ["Loading..."]:
            await wait_for_condition(
                pilot,
                lambda: bool(app._schema_cache.get("columns", {}).get("test.hello_world")),
                timeout_seconds=10.0,
                description="schema-qualified columns to load",
            )
            alias_columns = _suggestions(app, "SELECT * FROM test.hello_world h WHERE h.")

        assert {"id", "greeting"}.issubset({item.lower() for item in alias_columns})
        assert "Loading..." not in alias_columns
