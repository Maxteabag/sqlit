"""Integration tests for Docker container detection.

These tests require Docker to be installed and running on the machine.
They will be skipped if Docker is not available.

To run these tests:
    pytest tests/integration/docker_detect/ -v

To run with a temporary test container:
    pytest tests/integration/docker_detect/ -v --run-docker-container
"""

from __future__ import annotations

import subprocess
import time
from typing import TYPE_CHECKING

import pytest

from sqlit.services.docker_detector import (
    DockerStatus,
    detect_database_containers,
    get_docker_status,
)

if TYPE_CHECKING:
    pass


def is_docker_available() -> bool:
    """Check if Docker is available on this machine."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def is_docker_sdk_installed() -> bool:
    """Check if the Docker SDK is installed."""
    try:
        import docker  # noqa: F401

        return True
    except ImportError:
        return False


# Skip all tests in this module if Docker is not available
pytestmark = [
    pytest.mark.skipif(
        not is_docker_available(),
        reason="Docker is not available on this machine",
    ),
    pytest.mark.skipif(
        not is_docker_sdk_installed(),
        reason="Docker SDK (pip install docker) is not installed",
    ),
    pytest.mark.integration,
]


class TestDockerStatusIntegration:
    """Integration tests for Docker status detection."""

    def test_docker_status_available(self):
        """Test that Docker is detected as available when running."""
        status = get_docker_status()
        assert status == DockerStatus.AVAILABLE, f"Expected AVAILABLE, got {status}"

    def test_docker_sdk_can_connect(self):
        """Test that the Docker SDK can connect to the daemon."""
        import docker

        client = docker.from_env()
        # Should not raise
        info = client.info()
        assert "ServerVersion" in info


class TestContainerDetectionIntegration:
    """Integration tests for container detection."""

    def test_detect_returns_tuple(self):
        """Test that detect_database_containers returns proper tuple."""
        status, containers = detect_database_containers()

        assert isinstance(status, DockerStatus)
        assert isinstance(containers, list)
        assert status == DockerStatus.AVAILABLE

    def test_detect_existing_database_containers(self):
        """Test detection of any existing database containers.

        This test will pass if there are database containers running,
        or if there are none (it just verifies the detection works).
        """
        status, containers = detect_database_containers()

        assert status == DockerStatus.AVAILABLE

        # Log what we found for debugging
        if containers:
            print(f"\nFound {len(containers)} database container(s):")
            for c in containers:
                print(f"  - {c.container_name} ({c.db_type}) on port {c.port}")
        else:
            print("\nNo database containers currently running")

        # Verify container structure if any found
        for container in containers:
            assert container.container_id
            assert container.container_name
            assert container.db_type in [
                "postgresql",
                "mysql",
                "mariadb",
                "mssql",
                "clickhouse",
                "cockroachdb",
            ]
            assert container.host == "localhost"


class TestWithTemporaryContainer:
    """Tests that spin up a temporary container for testing.

    These tests are more comprehensive but require creating/destroying containers.
    Use --run-docker-container flag to enable these tests.
    """

    POSTGRES_IMAGE = "postgres:15-alpine"
    CONTAINER_NAME = "sqlit-test-postgres"
    TEST_PORT = 25432  # Use non-standard port to avoid conflicts

    @pytest.fixture
    def postgres_container(self, request):
        """Create a temporary PostgreSQL container for testing."""
        # Check if we should run container tests
        if not request.config.getoption("--run-docker-container", default=False):
            pytest.skip("Use --run-docker-container to run tests with temporary containers")

        import docker

        client = docker.from_env()

        # Clean up any existing test container
        try:
            existing = client.containers.get(self.CONTAINER_NAME)
            existing.stop()
            existing.remove()
        except docker.errors.NotFound:
            pass

        # Pull image if needed
        try:
            client.images.get(self.POSTGRES_IMAGE)
        except docker.errors.ImageNotFound:
            print(f"\nPulling {self.POSTGRES_IMAGE}...")
            client.images.pull(self.POSTGRES_IMAGE)

        # Create and start container
        container = client.containers.run(
            self.POSTGRES_IMAGE,
            name=self.CONTAINER_NAME,
            environment={
                "POSTGRES_USER": "testuser",
                "POSTGRES_PASSWORD": "testpass",
                "POSTGRES_DB": "testdb",
            },
            ports={"5432/tcp": self.TEST_PORT},
            detach=True,
            remove=True,  # Auto-remove when stopped
        )

        # Wait for container to be ready
        time.sleep(2)

        yield container

        # Cleanup
        try:
            container.stop(timeout=5)
        except Exception:
            pass

    def test_detect_postgres_container(self, postgres_container):
        """Test that a PostgreSQL container is properly detected."""
        # Give container a moment to fully start
        time.sleep(1)

        status, containers = detect_database_containers()

        assert status == DockerStatus.AVAILABLE

        # Find our test container
        test_container = next(
            (c for c in containers if c.container_name == self.CONTAINER_NAME),
            None,
        )

        assert test_container is not None, (
            f"Test container '{self.CONTAINER_NAME}' not found. "
            f"Found: {[c.container_name for c in containers]}"
        )

        # Verify detected properties
        assert test_container.db_type == "postgresql"
        assert test_container.host == "localhost"
        assert test_container.port == self.TEST_PORT
        assert test_container.username == "testuser"
        assert test_container.password == "testpass"
        assert test_container.database == "testdb"

    def test_container_to_connection_config(self, postgres_container):
        """Test converting detected container to ConnectionConfig."""
        from sqlit.services.docker_detector import container_to_connection_config

        time.sleep(1)

        status, containers = detect_database_containers()
        test_container = next(
            (c for c in containers if c.container_name == self.CONTAINER_NAME),
            None,
        )

        assert test_container is not None

        config = container_to_connection_config(test_container)

        assert config.name == self.CONTAINER_NAME
        assert config.db_type == "postgresql"
        assert config.server == "localhost"
        assert config.port == str(self.TEST_PORT)
        assert config.username == "testuser"
        assert config.password == "testpass"
        assert config.database == "testdb"
