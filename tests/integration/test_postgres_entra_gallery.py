"""Opt-in screenshots for PostgreSQL Azure Entra authentication."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from textual.widgets import Select

from sqlit.domains.connections.providers.postgresql.auth import (
    POSTGRES_AUTH_AZURE_ENTRA_CLI,
)
from sqlit.shared.app.runtime import MockConfig, RuntimeConfig
from tests.ui.conftest import ConnectionScreenTestApp
from tests.ui.mocks import build_test_services

_OUTPUT = os.environ.get("SQLIT_POSTGRES_ENTRA_SCREENSHOTS_DIR")
pytestmark = pytest.mark.skipif(not _OUTPUT, reason="screenshot output is not configured")


def _shot(app: ConnectionScreenTestApp, output: Path, name: str) -> None:
    app.save_screenshot(path=output, filename=f"{name}.svg")


@pytest.mark.asyncio
async def test_postgres_entra_connection_gallery() -> None:
    assert _OUTPUT is not None
    output = Path(_OUTPUT)
    output.mkdir(parents=True, exist_ok=True)
    for old in output.glob("*.svg"):
        old.unlink()

    services = build_test_services(
        runtime=RuntimeConfig(mock=MockConfig(enabled=True))
    )
    app = ConnectionScreenTestApp(
        prefill_values={"db_type": "postgresql"},
        services=services,
    )
    async with app.run_test(size=(112, 40)) as pilot:
        screen = app.screen
        screen.query_one("#conn-name").value = "azure-production"
        screen.query_one("#field-server").value = (
            "example.postgres.database.azure.com"
        )
        screen.query_one("#field-database").value = "appdb"
        screen.query_one("#field-username").value = "developer@example.com"
        await pilot.pause()
        _shot(app, output, "01-postgres-password-auth")

        auth = screen.query_one("#field-postgres_auth_method", Select)
        auth.focus()
        await pilot.press("enter")
        await pilot.pause()
        _shot(app, output, "02-postgres-auth-options")

        await pilot.press("down", "enter")
        await pilot.pause()
        assert auth.value == POSTGRES_AUTH_AZURE_ENTRA_CLI
        assert "hidden" in screen.query_one("#container-password").classes
        _shot(app, output, "03-postgres-entra-selected")
