"""Docker-specific integration tests shared across database types."""

from __future__ import annotations

import pytest


class DockerDiscoveryTests:
    """Mixin class providing Docker discovery tests."""

    def test_docker_container_detection(self, request):
        """Test that docker discovery detects the database container.

        This ensures that the docker auto-discovery feature can find
        containers for this database type in the connection picker.
        """
        # Skip for file-based databases (they don't use Docker containers)
        from sqlit.domains.connections.providers.registry import is_file_based

        if is_file_based(self.config.db_type):
            pytest.skip(f"{self.config.display_name} is file-based, no Docker container")

        from sqlit.domains.connections.discovery.docker_detector import (
            DockerStatus,
            detect_database_containers,
        )
        from sqlit.domains.connections.providers.catalog import get_provider

        # Skip if this database type has no Docker image patterns defined
        provider = get_provider(self.config.db_type)
        if provider.docker_detector is None:
            pytest.skip(f"{self.config.display_name} has no Docker image patterns")

        status, containers = detect_database_containers()

        if status != DockerStatus.AVAILABLE:
            pytest.skip("Docker is not available")

        # Find a container matching this database type
        matching_containers = [
            c for c in containers if c.db_type == self.config.db_type
        ]

        assert len(matching_containers) > 0, (
            f"No Docker container detected for {self.config.display_name}. "
            f"Found containers: {[(c.container_name, c.db_type) for c in containers]}"
        )

        # Verify the container has a port detected
        container = matching_containers[0]
        assert container.port is not None, (
            f"Container {container.container_name} has no port detected"
        )

    def test_docker_container_no_password_prompt_when_not_needed(self, request):
        """Test that docker discovery doesn't trigger password prompts for no-auth databases.

        Some databases (CockroachDB, Turso) can run without authentication in
        local/insecure mode. When docker discovery detects these containers,
        it should return password="" (empty string) rather than password=None.

        - password=None means "not set" -> UI will prompt for password
        - password="" means "explicitly empty" -> UI will NOT prompt

        This test ensures users aren't asked for passwords for databases
        that don't need them.
        """
        # Skip for file-based databases (they don't use Docker containers)
        from sqlit.domains.connections.providers.registry import is_file_based

        if is_file_based(self.config.db_type):
            pytest.skip(f"{self.config.display_name} is file-based, no Docker container")

        from sqlit.domains.connections.discovery.docker_detector import (
            DockerStatus,
            container_to_connection_config,
            detect_database_containers,
        )

        status, containers = detect_database_containers()

        if status != DockerStatus.AVAILABLE:
            pytest.skip("Docker is not available")

        # Find a container matching this database type
        matching_containers = [
            c for c in containers if c.db_type == self.config.db_type
        ]

        if not matching_containers:
            pytest.skip(f"No Docker container found for {self.config.display_name}")

        container = matching_containers[0]
        config = container_to_connection_config(container)

        # Databases that don't require auth should have password="" not None
        # This prevents the UI from showing "Password Required" dialog
        from sqlit.domains.connections.providers.registry import requires_auth

        if not requires_auth(self.config.db_type):
            assert config.password is not None, (
                f"{self.config.display_name} doesn't require authentication, but "
                f"password is None. This will cause the UI to prompt for a password. "
                f"Set password='' (empty string) in docker_detector.py for databases "
                f"that don't need auth."
            )

    def test_docker_container_connection(self, request):
        """Test that docker-discovered credentials actually work.

        This tests the full docker discovery flow:
        1. Detect the container
        2. Convert to ConnectionConfig
        3. Connect using discovered credentials
        4. Run a simple query

        This catches issues like:
        - Wrong host (localhost vs 127.0.0.1 for MySQL/MariaDB)
        - Missing or incorrect credentials
        - Wrong port mappings
        """
        # Skip for file-based databases (they don't use Docker containers)
        from sqlit.domains.connections.providers.registry import is_file_based

        if is_file_based(self.config.db_type):
            pytest.skip(f"{self.config.display_name} is file-based, no Docker container")

        from sqlit.domains.connections.discovery.docker_detector import (
            DockerStatus,
            container_to_connection_config,
            detect_database_containers,
        )
        from sqlit.domains.connections.providers.registry import get_adapter

        status, containers = detect_database_containers()

        if status != DockerStatus.AVAILABLE:
            pytest.skip("Docker is not available")

        # Find a container matching this database type
        matching_containers = [
            c for c in containers if c.db_type == self.config.db_type
        ]

        if not matching_containers:
            pytest.skip(f"No Docker container found for {self.config.display_name}")

        container = matching_containers[0]
        if not container.connectable:
            pytest.skip(f"Container {container.container_name} is not connectable")

        # Convert to ConnectionConfig (this is what the UI does)
        config = container_to_connection_config(container)

        # Databases that don't require auth should have password="" not None
        # This prevents the UI from showing "Password Required" dialog
        from sqlit.domains.connections.providers.registry import requires_auth

        if not requires_auth(self.config.db_type):
            assert config.password is not None, (
                f"{self.config.display_name} doesn't require authentication, but "
                f"password is None. This will cause the UI to prompt for a password. "
                f"Set password='' (empty string) in docker_detector.py for databases "
                f"that don't need auth."
            )

        # Connect and run a simple query to verify credentials
        adapter = get_adapter(self.config.db_type)
        conn = adapter.connect(config)
        try:
            adapter.execute_query(conn, "SELECT 1")
        finally:
            adapter.disconnect(conn)
