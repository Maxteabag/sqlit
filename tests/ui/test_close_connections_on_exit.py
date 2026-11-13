"""Open database connections are closed explicitly when the app exits."""

from __future__ import annotations

import pytest

from sqlit.domains.shell.app.main import SSMSTUI

from .mocks import MockConnectionStore, MockSettingsStore, build_test_services


class _Closable:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


@pytest.mark.asyncio
async def test_exit_closes_session_and_transaction_executor() -> None:
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({}),
    )
    app = SSMSTUI(services=services)
    session = _Closable()
    executor = _Closable()

    async with app.run_test() as pilot:
        app._session = session
        app._transaction_executor = executor
        await pilot.pause()

    assert session.close_calls == 1
    assert executor.close_calls == 1
    assert app._session is None
    assert app._transaction_executor is None
