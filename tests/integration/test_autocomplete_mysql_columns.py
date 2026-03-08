"""Integration tests for MySQL autocomplete column suggestions."""

from __future__ import annotations

import os
import tempfile

import pytest

from sqlit.domains.shell.app.main import SSMSTUI
from tests.fixtures.mysql import MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER
from tests.helpers import ConnectionConfig
from tests.integration.browsing_base import wait_for_condition


EXTRA_DB_NAME = os.environ.get("MYSQL_AUTOCOMPLETE_EXTRA_DB", "test_sqlit_autocomplete_other")


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
def mysql_extra_db(mysql_server_ready: bool):
    """Create a second user database to force multi-db autocomplete mode."""
    if not mysql_server_ready:
        pytest.skip("MySQL is not available")

    try:
        import pymysql
    except ImportError:
        pytest.skip("PyMySQL is not installed")

    conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database="mysql",
        connect_timeout=10,
    )
    cursor = conn.cursor()
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{EXTRA_DB_NAME}`")
    conn.commit()
    conn.close()

    yield EXTRA_DB_NAME

    conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database="mysql",
        connect_timeout=10,
    )
    cursor = conn.cursor()
    cursor.execute(f"DROP DATABASE IF EXISTS `{EXTRA_DB_NAME}`")
    conn.commit()
    conn.close()


def _set_cursor_to_end(app: SSMSTUI) -> None:
    text = app.query_input.text
    lines = text.split("\n")
    app.query_input.cursor_location = (len(lines) - 1, len(lines[-1]) if lines else 0)


@pytest.mark.asyncio
async def test_mysql_alias_autocomplete_shows_columns_multi_db(
    mysql_server_ready: bool,
    mysql_db: str,
    mysql_extra_db: str,  # noqa: ARG001 - fixture used for setup/teardown
    temp_config_dir: str,  # noqa: ARG001 - fixture used for isolation
) -> None:
    """Autocomplete should resolve alias columns even with multi-db schema cache."""
    if not mysql_server_ready:
        pytest.skip("MySQL is not available")

    config = ConnectionConfig(
        name="test-mysql-autocomplete",
        db_type="mysql",
        server=MYSQL_HOST,
        port=str(MYSQL_PORT),
        database="",
        username=MYSQL_USER,
        password=MYSQL_PASSWORD,
    )

    app = SSMSTUI()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)

        app.connections = [config]
        app.refresh_tree()
        await pilot.pause(0.1)

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

        # Ensure schema cache is available for autocomplete in headless tests.
        load_schema_async = getattr(app, "_load_schema_cache_async", None)
        if callable(load_schema_async):
            await load_schema_async()

        await wait_for_condition(
            pilot,
            lambda: (
                "test_users" in getattr(app, "_table_metadata", {})
                or f"{mysql_db}.test_users" in getattr(app, "_table_metadata", {})
            ),
            timeout_seconds=20.0,
            description="table metadata to be loaded",
        )

        app.query_input.text = f"SELECT * FROM {mysql_db}.test_users u WHERE u."
        _set_cursor_to_end(app)
        app._trigger_autocomplete(app.query_input)

        expected = {"id", "name", "email"}

        await wait_for_condition(
            pilot,
            lambda: bool(app._schema_cache.get("columns", {}).get("test_users")),
            timeout_seconds=10.0,
            description="autocomplete columns to load",
        )

        text = app.query_input.text
        cursor_loc = app.query_input.cursor_location
        cursor_pos = app._location_to_offset(text, cursor_loc)
        suggestions = app._get_autocomplete_suggestions(text, cursor_pos)
        assert expected.issubset({item.lower() for item in suggestions})
        assert "Loading..." not in suggestions
