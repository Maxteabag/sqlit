"""Regression coverage for SQLite session state in the TUI's Run All path."""

from contextlib import closing

import pytest

from sqlit.domains.connections.providers.registry import get_provider
from sqlit.domains.query.app.query_service import QueryResult
from sqlit.domains.shell.app.main import SSMSTUI
from tests.ui.mocks import (
    MockConnectionStore,
    MockSettingsStore,
    build_test_services,
    create_test_connection,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("in_memory", [False, True], ids=["file", "memory"])
async def test_sqlite_script_keeps_temp_tables(tmp_path, monkeypatch, in_memory):
    path = ":memory:" if in_memory else str(tmp_path / "test.sqlite")
    config = create_test_connection("test-sqlite", "sqlite", file_path=path)
    app = SSMSTUI(services=build_test_services(
        connection_store=MockConnectionStore([config]),
        settings_store=MockSettingsStore({}),
    ))
    results = []

    display_results = app._display_multi_statement_results

    def capture_results(result, elapsed_ms):
        display_results(result, elapsed_ms)
        results.append(result)

    monkeypatch.setattr(app, "_display_multi_statement_results", capture_results)

    monkeypatch.setattr(app, "_display_non_query_result", lambda *_: None)

    provider = get_provider("sqlite")
    with closing(provider.connection_factory.connect(config)) as connection:
        await check_scripts(app, config, provider, connection, results)


async def check_scripts(app, config, provider, connection, results):
    async with app.run_test(size=(120, 40)) as pilot:
        app.current_config = config
        app.current_provider = provider
        app.current_connection = connection

        async def run(sql):
            app.query_input.text = sql
            app.action_execute_query()
            await app._query_worker.wait()
            await pilot.pause()

        async def run_script(sql):
            await run(sql)
            assert results[-1].completed, results[-1].results[-1].error
            result = results[-1].results[-1].result
            assert isinstance(result, QueryResult)
            return result.rows

        assert await run_script(
            "CREATE TEMP TABLE sample(v INT); INSERT INTO sample VALUES (73); SELECT * FROM sample;"
        ) == [(73,)]

        await run("BEGIN")
        assert app.in_transaction
        assert await run_script(
            "CREATE TEMP TABLE sample(v INT); INSERT INTO sample VALUES (73); COMMIT;"
            "BEGIN; INSERT INTO sample VALUES (99); SELECT * FROM sample; ROLLBACK;"
            "SELECT * FROM sample;"
        ) == [(73,)]
        assert not app.in_transaction

        assert await run_script(
            "SELECT 1; SELECT name FROM sqlite_temp_master WHERE name = 'sample';"
        ) == []
