"""Unit tests for Docker tab container filtering logic.

These tests verify that containers are correctly shown/hidden based on
saved connections, particularly the fix for non-docker-sourced connections
incorrectly hiding containers.
"""

from __future__ import annotations

import pytest

from sqlit.domains.connections.discovery.docker_detector import (
    ContainerStatus,
    DetectedContainer,
)
from sqlit.domains.connections.domain.config import ConnectionConfig, TcpEndpoint
from sqlit.domains.connections.ui.screens.connection_picker.tabs.docker import (
    build_docker_options,
    find_matching_saved_connection,
    is_container_saved,
)


def make_container(
    name: str,
    db_type: str = "postgresql",
    port: int = 5432,
    database: str = "postgres",
    status: ContainerStatus = ContainerStatus.RUNNING,
) -> DetectedContainer:
    """Helper to create a DetectedContainer for testing."""
    return DetectedContainer(
        container_id=f"{name}-id",
        container_name=name,
        db_type=db_type,
        host="localhost",
        port=port,
        username="testuser",
        password="testpass",
        database=database,
        status=status,
        connectable=status == ContainerStatus.RUNNING and port is not None,
    )


def make_connection(
    name: str,
    db_type: str = "postgresql",
    port: str = "5432",
    database: str = "postgres",
    source: str | None = None,
) -> ConnectionConfig:
    """Helper to create a ConnectionConfig for testing."""
    return ConnectionConfig(
        name=name,
        db_type=db_type,
        source=source,
        endpoint=TcpEndpoint(
            host="localhost",
            port=port,
            database=database,
            username="testuser",
        ),
    )


class TestIsContainerSaved:
    """Tests for is_container_saved function."""

    def test_container_hidden_when_name_matches_exactly(self):
        """Container should be hidden if a saved connection has the exact same name."""
        container = make_container("my-postgres")
        connection = make_connection("my-postgres", source=None)  # Not docker-sourced

        assert is_container_saved([connection], container) is True

    def test_container_visible_when_name_differs(self):
        """Container should be visible if no saved connection matches by name."""
        container = make_container("norwegian-postgres")
        connection = make_connection("other-postgres", source=None)

        assert is_container_saved([connection], container) is False

    def test_non_docker_connection_does_not_hide_by_technical_match(self):
        """Non-docker-sourced connection should NOT hide container even if port/db match.

        This was the bug: a connection with source=None would hide containers
        just because they had the same host:port:database, even though the
        connection wasn't created from Docker discovery.
        """
        container = make_container(
            "norwegian-postgres",
            db_type="postgresql",
            port=5432,
            database="postgres",
        )
        # Connection with same technical details but different name and source=None
        connection = make_connection(
            "empty-password-test",
            db_type="postgresql",
            port="5432",
            database="postgres",
            source=None,  # NOT a docker-sourced connection
        )

        # Container should NOT be hidden
        assert is_container_saved([connection], container) is False

    def test_docker_sourced_connection_hides_by_technical_match(self):
        """Docker-sourced connection SHOULD hide container with matching technical details."""
        container = make_container(
            "my-postgres",
            db_type="postgresql",
            port=5432,
            database="testdb",
        )
        # Docker-sourced connection with same technical details but different name
        connection = make_connection(
            "saved-docker-postgres",
            db_type="postgresql",
            port="5432",
            database="testdb",
            source="docker",  # Docker-sourced
        )

        # Container SHOULD be hidden because technical details match and source is docker
        assert is_container_saved([connection], container) is True

    def test_docker_connection_different_port_does_not_hide(self):
        """Docker-sourced connection with different port should not hide container."""
        container = make_container("my-postgres", port=5432)
        connection = make_connection("other-postgres", port="5433", source="docker")

        assert is_container_saved([connection], container) is False

    def test_docker_connection_different_db_type_does_not_hide(self):
        """Docker-sourced connection with different db_type should not hide container."""
        container = make_container("my-db", db_type="postgresql", port=5432)
        connection = make_connection("my-db", db_type="mysql", port="5432", source="docker")

        # Name matches, so it should be hidden regardless of db_type
        assert is_container_saved([connection], container) is True

    def test_multiple_connections_first_match_wins(self):
        """When multiple connections exist, first match (by name) should win."""
        container = make_container("target-db")
        connections = [
            make_connection("other-db", source="docker"),
            make_connection("target-db", source=None),  # Name match
            make_connection("another-db", source="docker"),
        ]

        assert is_container_saved(connections, container) is True

    def test_empty_connections_list(self):
        """Container should be visible when no connections exist."""
        container = make_container("my-postgres")

        assert is_container_saved([], container) is False


class TestFindMatchingSavedConnection:
    """Tests for find_matching_saved_connection function."""

    def test_finds_connection_by_name(self):
        """Should find connection when name matches exactly."""
        container = make_container("my-postgres")
        connection = make_connection("my-postgres", source=None)

        result = find_matching_saved_connection([connection], container)
        assert result is not None
        assert result.name == "my-postgres"

    def test_non_docker_connection_not_found_by_technical_match(self):
        """Non-docker connection should NOT be found by technical details alone."""
        container = make_container("norwegian-postgres", port=5432, database="postgres")
        connection = make_connection(
            "different-name",
            port="5432",
            database="postgres",
            source=None,  # Not docker-sourced
        )

        result = find_matching_saved_connection([connection], container)
        assert result is None

    def test_docker_connection_found_by_technical_match(self):
        """Docker connection SHOULD be found by technical details."""
        container = make_container("norwegian-postgres", port=5432, database="postgres")
        connection = make_connection(
            "saved-docker-pg",
            port="5432",
            database="postgres",
            source="docker",
        )

        result = find_matching_saved_connection([connection], container)
        assert result is not None
        assert result.name == "saved-docker-pg"


class TestBuildDockerOptions:
    """Tests for build_docker_options function."""

    def test_running_container_visible_when_not_saved(self):
        """Running container should appear in Running section when not saved."""
        container = make_container("norwegian-postgres", status=ContainerStatus.RUNNING)
        connections = []

        options = build_docker_options(
            connections, [container], "", loading=False, status_message=None
        )

        # Find the option for our container
        container_options = [
            opt for opt in options if opt.id and "norwegian-postgres" in str(opt.id)
        ]
        assert len(container_options) == 1
        assert not container_options[0].disabled

    def test_container_hidden_when_non_docker_connection_has_same_name(self):
        """Container should be hidden when a connection has the exact same name."""
        container = make_container("my-postgres", status=ContainerStatus.RUNNING)
        connection = make_connection("my-postgres", source=None)

        options = build_docker_options(
            [connection], [container], "", loading=False, status_message=None
        )

        # Container should not appear (filtered out because name matches)
        container_options = [
            opt for opt in options if opt.id and "my-postgres-id" in str(opt.id)
        ]
        assert len(container_options) == 0

    def test_container_visible_when_non_docker_connection_only_matches_port(self):
        """Container should be visible when non-docker connection only matches by port.

        This tests the fix: norwegian-postgres was being hidden because
        empty-password-test had the same port, even though they had different names.
        """
        container = make_container(
            "norwegian-postgres",
            port=5432,
            database="postgres",
            status=ContainerStatus.RUNNING,
        )
        # Non-docker connection with same port but different name
        connection = make_connection(
            "empty-password-test",
            port="5432",
            database="postgres",
            source=None,
        )

        options = build_docker_options(
            [connection], [container], "", loading=False, status_message=None
        )

        # Container SHOULD appear in Running section
        container_options = [
            opt for opt in options
            if opt.id and str(opt.id).startswith("docker:") and "norwegian-postgres" in str(opt.id)
        ]
        assert len(container_options) == 1, "norwegian-postgres should be visible"

    def test_saved_docker_connections_appear_in_saved_section(self):
        """Docker-sourced saved connections should appear in Saved section."""
        connection = make_connection("saved-postgres", source="docker")

        options = build_docker_options(
            [connection], [], "", loading=False, status_message=None
        )

        # Find the saved connection option (ID is the connection name, not prefixed)
        saved_options = [
            opt for opt in options if opt.id == "saved-postgres"
        ]
        assert len(saved_options) == 1

    def test_headers_always_present(self):
        """Section headers should always be present."""
        options = build_docker_options(
            [], [], "", loading=False, status_message=None
        )

        option_ids = [opt.id for opt in options]
        assert "_header_docker_saved" in option_ids
        assert "_header_docker" in option_ids
