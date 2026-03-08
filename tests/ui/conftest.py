"""Pytest fixtures for UI (Pilot) tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from textual.app import App

from sqlit.domains.connections.ui.screens import ConnectionScreen
from tests.helpers import ConnectionConfig

from .mocks import (
    MockAdapterRegistry,
    MockConnectionStore,
    MockDatabaseAdapter,
    MockHistoryStore,
    MockSettingsStore,
    build_test_services,
    create_test_connection,
)


class ConnectionScreenTestApp(App):
    def __init__(
        self,
        config: ConnectionConfig | None = None,
        editing: bool = False,
        prefill_values: dict | None = None,
        services=None,
    ):
        super().__init__()
        self._config = config
        self._editing = editing
        self._prefill_values = prefill_values
        self.screen_result = None
        self.services = services or build_test_services(
            connection_store=MockConnectionStore(),
            settings_store=MockSettingsStore({"theme": "tokyo-night"}),
        )

    async def on_mount(self) -> None:
        screen = ConnectionScreen(
            self._config, editing=self._editing, prefill_values=self._prefill_values
        )
        await self.push_screen(screen, self._capture_result)

    def _capture_result(self, result) -> None:
        self.screen_result = result


@pytest.fixture
def mock_connection_store():
    """Provide an empty mock connection store."""
    return MockConnectionStore()


@pytest.fixture
def mock_connection_store_with_data():
    """Provide a mock connection store with sample connections."""
    connections = [
        create_test_connection("prod-db", "postgresql", server="prod.example.com"),
        create_test_connection("local-sqlite", "sqlite", file_path="/home/user/data.db"),
        create_test_connection("dev-mysql", "mysql", server="localhost", port="3306"),
    ]
    return MockConnectionStore(connections)


@pytest.fixture
def mock_history_store():
    """Provide an empty mock history store."""
    return MockHistoryStore()


@pytest.fixture
def mock_settings_store():
    """Provide a mock settings store with default theme."""
    return MockSettingsStore({"theme": "tokyo-night"})


@pytest.fixture
def mock_adapter_registry():
    """Provide a mock adapter registry."""
    registry = MockAdapterRegistry()
    # Register default adapters for common types
    registry.register("sqlite", MockDatabaseAdapter(name="SQLite"))
    registry.register("postgresql", MockDatabaseAdapter(name="PostgreSQL"))
    registry.register("mysql", MockDatabaseAdapter(name="MySQL"))
    registry.register("mssql", MockDatabaseAdapter(name="SQL Server"))
    return registry


@pytest.fixture
def mock_failing_adapter():
    """Provide an adapter that fails to connect."""
    return MockDatabaseAdapter(
        name="FailingDB",
        should_fail_connect=True,
        connect_error="Could not connect to database",
    )


@pytest.fixture
def patch_stores(mock_connection_store, mock_settings_store):
    """Patch all stores with mocks for isolated testing."""
    services = build_test_services(
        connection_store=mock_connection_store,
        settings_store=mock_settings_store,
    )
    yield {
        "connections": mock_connection_store,
        "settings": mock_settings_store,
        "services": services,
    }


@pytest.fixture
def patch_stores_with_data(mock_connection_store_with_data, mock_settings_store):
    """Patch stores with sample data."""
    services = build_test_services(
        connection_store=mock_connection_store_with_data,
        settings_store=mock_settings_store,
    )
    yield {
        "connections": mock_connection_store_with_data,
        "settings": mock_settings_store,
        "services": services,
    }


@pytest.fixture
def patch_adapter(mock_adapter_registry):
    """Patch get_adapter to return mock adapters."""
    with patch("sqlit.domains.connections.providers.get_adapter", mock_adapter_registry.get_adapter):
        yield mock_adapter_registry
