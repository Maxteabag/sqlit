"""Tests for password input screen and connection flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest
from textual.widgets import Input

from sqlit.domains.connections.providers.model import SchemaCapabilities
from sqlit.domains.connections.providers.explorer_nodes import DefaultExplorerNodeProvider
from sqlit.domains.connections.ui.screens.password_input import PasswordInputScreen
from sqlit.shared.app.runtime import MockConfig, RuntimeConfig
from tests.helpers import ConnectionConfig

from .mocks import build_test_services


@dataclass
class MockProvider:
    capabilities: SchemaCapabilities
    schema_inspector: object | None = None
    explorer_nodes: object = field(default_factory=DefaultExplorerNodeProvider)

    def post_connect_warnings(self, _config: ConnectionConfig) -> list[str]:
        return []


def _make_provider(default_schema: str = "") -> MockProvider:
    return MockProvider(
        capabilities=SchemaCapabilities(
            supports_multiple_databases=False,
            supports_cross_database_queries=False,
            supports_stored_procedures=False,
            supports_indexes=False,
            supports_triggers=False,
            supports_sequences=False,
            default_schema=default_schema,
            system_databases=frozenset(),
        )
    )
class TestPasswordInputScreen:
    """Test the PasswordInputScreen modal."""

    @pytest.mark.asyncio
    async def test_password_input_screen_renders(self) -> None:
        """Password input screen renders with correct title and description."""
        from textual.app import App

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            screen = PasswordInputScreen("test_connection")
            app.push_screen(screen)
            await pilot.pause()

            # Check that the input field exists (password visible for usability)
            input_widget = screen.query_one("#password-input", Input)
            assert input_widget is not None
            assert input_widget.password is False

    @pytest.mark.asyncio
    async def test_password_input_submit_with_enter(self) -> None:
        """Pressing Enter submits the password."""
        from textual.app import App

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            result = None

            def on_dismiss(password):
                nonlocal result
                result = password

            screen = PasswordInputScreen("test_connection")
            app.push_screen(screen, on_dismiss)
            await pilot.pause()

            # Type a password
            input_widget = screen.query_one("#password-input", Input)
            input_widget.value = "my_secret_password"
            await pilot.pause()

            # Press Enter to submit
            await pilot.press("enter")
            await pilot.pause()

            # Should have dismissed with the password
            assert result == "my_secret_password"

    @pytest.mark.asyncio
    async def test_password_input_cancel_with_escape(self) -> None:
        """Pressing Escape cancels and returns None."""
        from textual.app import App

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            result = "not_set"

            def on_dismiss(password):
                nonlocal result
                result = password

            screen = PasswordInputScreen("test_connection")
            app.push_screen(screen, on_dismiss)
            await pilot.pause()

            # Type a password but then cancel
            input_widget = screen.query_one("#password-input", Input)
            input_widget.value = "my_secret_password"
            await pilot.pause()

            # Press Escape to cancel
            await pilot.press("escape")
            await pilot.pause()

            # Should have dismissed with None
            assert result is None

    @pytest.mark.asyncio
    async def test_password_input_shows_connection_name(self) -> None:
        """Password input shows the connection name in description."""
        from textual.app import App
        from textual.widgets import Static

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            screen = PasswordInputScreen("my_database")
            app.push_screen(screen)
            await pilot.pause()

            description = screen.query_one("#password-description", Static)
            assert "my_database" in str(description.render())

    @pytest.mark.asyncio
    async def test_password_input_ssh_type(self) -> None:
        """SSH password type shows appropriate message."""
        from textual.app import App
        from textual.widgets import Static

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            screen = PasswordInputScreen("test_connection", password_type="ssh")
            app.push_screen(screen)
            await pilot.pause()

            description = screen.query_one("#password-description", Static)
            rendered_text = str(description.render())
            assert "SSH password" in rendered_text
            assert "test_connection" in rendered_text

    @pytest.mark.asyncio
    async def test_password_input_custom_description(self) -> None:
        """Custom description is displayed."""
        from textual.app import App
        from textual.widgets import Static

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            screen = PasswordInputScreen(
                "test_connection",
                description="Please enter your custom password:",
            )
            app.push_screen(screen)
            await pilot.pause()

            description = screen.query_one("#password-description", Static)
            assert "custom password" in str(description.render())

    @pytest.mark.asyncio
    async def test_password_visible_in_input(self) -> None:
        """Password characters are visible when typing for usability."""
        from textual.app import App

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            screen = PasswordInputScreen("test_connection")
            app.push_screen(screen)
            await pilot.pause()

            input_widget = screen.query_one("#password-input", Input)
            input_widget.value = "secret123"
            await pilot.pause()

            # Password is visible for better usability in terminal apps
            assert input_widget.password is False


class TestConnectionPasswordFlow:
    """Test the connection flow with password prompts."""

    @pytest.mark.asyncio
    async def test_connect_with_none_password_shows_prompt(self) -> None:
        """Connecting with None password shows password input screen."""
        from sqlit.domains.connections.app.mocks import get_mock_profile
        from sqlit.domains.shell.app.main import SSMSTUI

        mock_profile = get_mock_profile("empty")
        runtime = RuntimeConfig(mock=MockConfig(enabled=True, profile=mock_profile))
        services = build_test_services(runtime=runtime)
        app = SSMSTUI(services=services)

        async with app.run_test() as pilot:
            # Create a connection with None password (not set)
            config = ConnectionConfig(
                name="test_db",
                db_type="postgresql",
                server="localhost",
                username="user",
                password=None,  # None = prompt needed
            )
            app.connections = [config]

            # Trigger connect
            app.connect_to_server(config)
            await pilot.pause()

            # Should have pushed PasswordInputScreen
            assert isinstance(app.screen, PasswordInputScreen)
            assert app.screen.connection_name == "test_db"

    @pytest.mark.asyncio
    async def test_connect_with_stored_password_no_prompt(self) -> None:
        """Connecting with stored password doesn't show prompt."""
        from sqlit.domains.connections.app.mocks import get_mock_profile
        from sqlit.domains.shell.app.main import SSMSTUI

        mock_profile = get_mock_profile("empty")
        runtime = RuntimeConfig(mock=MockConfig(enabled=True, profile=mock_profile))
        services = build_test_services(runtime=runtime)
        app = SSMSTUI(services=services)

        async with app.run_test() as pilot:
            # Create a connection with stored password
            config = ConnectionConfig(
                name="test_db",
                db_type="postgresql",
                server="localhost",
                username="user",
                password="stored_password",
            )
            app.connections = [config]

            # Mock the session factory
            mock_session = MagicMock()
            mock_session.connection = MagicMock()
            mock_session.provider = _make_provider()
            mock_session.tunnel = None
            mock_session.config = config

            services.session_factory = lambda c: mock_session

            # Trigger connect
            app.connect_to_server(config)
            await pilot.pause(0.5)  # Wait for worker thread

            # Should NOT have pushed PasswordInputScreen
            # (the app screen should be the main app, not PasswordInputScreen)
            assert not isinstance(app.screen, PasswordInputScreen)

    @pytest.mark.asyncio
    async def test_ssh_password_prompt_before_db_password(self) -> None:
        """SSH password is prompted before database password."""
        from sqlit.domains.connections.app.mocks import get_mock_profile
        from sqlit.domains.shell.app.main import SSMSTUI

        mock_profile = get_mock_profile("empty")
        runtime = RuntimeConfig(mock=MockConfig(enabled=True, profile=mock_profile))
        services = build_test_services(runtime=runtime)
        app = SSMSTUI(services=services)

        async with app.run_test() as pilot:
            # Create a connection with SSH enabled and both passwords None (not set)
            config = ConnectionConfig(
                name="test_db",
                db_type="postgresql",
                server="localhost",
                username="user",
                password=None,  # None = prompt needed
                ssh_enabled=True,
                ssh_auth_type="password",
                ssh_host="bastion.example.com",
                ssh_username="sshuser",
                ssh_password=None,  # None = prompt needed
            )
            app.connections = [config]

            # Trigger connect
            app.connect_to_server(config)
            await pilot.pause()

            # Should have pushed PasswordInputScreen for SSH first
            assert isinstance(app.screen, PasswordInputScreen)
            assert app.screen.password_type == "ssh"

    @pytest.mark.asyncio
    async def test_cancel_password_prompt_aborts_connection(self) -> None:
        """Cancelling password prompt aborts the connection."""
        from sqlit.domains.connections.app.mocks import get_mock_profile
        from sqlit.domains.shell.app.main import SSMSTUI

        mock_profile = get_mock_profile("empty")
        runtime = RuntimeConfig(mock=MockConfig(enabled=True, profile=mock_profile))
        services = build_test_services(runtime=runtime)
        app = SSMSTUI(services=services)

        async with app.run_test() as pilot:
            # Create a connection with None password (not set)
            config = ConnectionConfig(
                name="test_db",
                db_type="postgresql",
                server="localhost",
                username="user",
                password=None,  # None = prompt needed
            )
            app.connections = [config]

            # Trigger connect
            app.connect_to_server(config)
            await pilot.pause()

            # Should show password prompt
            assert isinstance(app.screen, PasswordInputScreen)

            # Cancel the prompt
            await pilot.press("escape")
            await pilot.pause()

            # Should not have connected (current_connection should be None)
            assert app.current_connection is None

    @pytest.mark.asyncio
    async def test_password_from_prompt_used_for_connection(self) -> None:
        """Password entered in prompt is used for connection."""
        from sqlit.domains.connections.app.mocks import get_mock_profile
        from sqlit.domains.shell.app.main import SSMSTUI

        mock_profile = get_mock_profile("empty")
        runtime = RuntimeConfig(mock=MockConfig(enabled=True, profile=mock_profile))
        services = build_test_services(runtime=runtime)
        app = SSMSTUI(services=services)

        # Track what config was used for connection
        connection_config = None

        def mock_session_factory(config):
            nonlocal connection_config
            connection_config = config
            mock_session = MagicMock()
            mock_session.connection = MagicMock()
            mock_session.provider = _make_provider()
            mock_session.tunnel = None
            mock_session.config = config
            return mock_session

        services.session_factory = mock_session_factory

        async with app.run_test() as pilot:
            # Create a connection with None password (not set)
            config = ConnectionConfig(
                name="test_db",
                db_type="postgresql",
                server="localhost",
                username="user",
                password=None,  # None = prompt needed
            )
            app.connections = [config]

            # Trigger connect
            app.connect_to_server(config)
            await pilot.pause()

            # Should show password prompt
            assert isinstance(app.screen, PasswordInputScreen)

            # Enter password
            input_widget = app.screen.query_one("#password-input", Input)
            input_widget.value = "entered_password"
            await pilot.pause()

            # Submit
            await pilot.press("enter")
            await pilot.pause(0.5)  # Wait for connection worker

            # Check that the connection was made with the entered password
            assert connection_config is not None
            assert connection_config.password == "entered_password"
            # Original config should still have None password
            assert config.password is None

    @pytest.mark.asyncio
    async def test_file_based_database_no_password_prompt(self) -> None:
        """File-based databases (SQLite) don't prompt for password."""
        from sqlit.domains.connections.app.mocks import get_mock_profile
        from sqlit.domains.shell.app.main import SSMSTUI

        mock_profile = get_mock_profile("sqlite-demo")
        runtime = RuntimeConfig(mock=MockConfig(enabled=True, profile=mock_profile))
        services = build_test_services(runtime=runtime)
        app = SSMSTUI(services=services)

        async with app.run_test() as pilot:
            # Get the SQLite demo connection
            if app.connections:
                config = app.connections[0]

                # Trigger connect
                app.connect_to_server(config)
                await pilot.pause(0.5)

                # Should NOT show password prompt (SQLite doesn't need passwords)
                assert not isinstance(app.screen, PasswordInputScreen)
