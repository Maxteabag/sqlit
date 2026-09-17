"""Tests for the :s / :suspend command."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sqlit.domains.shell.app.main import SSMSTUI

from .mocks import MockConnectionStore, MockSettingsStore, build_test_services


def _make_app() -> SSMSTUI:
    return SSMSTUI(
        services=build_test_services(
            connection_store=MockConnectionStore(),
            settings_store=MockSettingsStore({"theme": "tokyo-night"}),
        )
    )


@pytest.mark.parametrize("command", ["s", "suspend", "S", " SUSPEND "])
def test_suspend_command_uses_textual_process_suspension(command: str) -> None:
    app = _make_app()
    app.action_suspend_process = MagicMock()  # type: ignore[method-assign]

    app._run_command(command)

    app.action_suspend_process.assert_called_once_with()


def test_suspend_command_is_listed() -> None:
    app = _make_app()
    captured: list[tuple[list[str], list[tuple[str, str, str, str]]]] = []
    app._replace_results_table = (  # type: ignore[method-assign]
        lambda columns, rows: captured.append((columns, rows))
    )

    app._show_command_list()

    _columns, rows = captured[0]
    assert ("General", ":s, :suspend", "Suspend sqlit; resume with fg", "Unix only") in rows
