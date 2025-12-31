"""Integration tests for Docker detection across all supported database types.

These tests spin up real database containers and verify detection works correctly.
They are slow and require Docker, so they're opt-in via --run-docker-container flag.

To run:
    pytest tests/integration/docker_detect/test_all_databases.py -v --run-docker-container
"""

from __future__ import annotations

import time

import pytest

from tests.integration.docker_detect.database_configs import (
    DATABASE_CONFIGS,
    DatabaseTestConfig,
)


def is_docker_available() -> bool:
    """Check if Docker is available."""
    import subprocess

    try:
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def is_docker_sdk_installed() -> bool:
    """Check if Docker SDK is installed."""
    try:
        import docker  # noqa: F401

        return True
    except ImportError:
        return False


pytestmark = [
    pytest.mark.skipif(not is_docker_available(), reason="Docker not available"),
    pytest.mark.skipif(not is_docker_sdk_installed(), reason="Docker SDK not installed"),
    pytest.mark.integration,
]


class TestAllDatabases:
    """Parameterized tests for all database types."""

    @pytest.fixture
    def docker_client(self):
        """Get Docker client."""
        import docker

        return docker.from_env()

    @pytest.fixture
    def container(self, request, docker_client):
        """Create and manage a test container."""
        if not request.config.getoption("--run-docker-container", default=False):
            pytest.skip("Use --run-docker-container to run container tests")

        config: DatabaseTestConfig = request.param
        container_name = f"sqlit-test-{config.name}"

        # Cleanup any existing container
        try:
            existing = docker_client.containers.get(container_name)
            existing.stop(timeout=5)
            existing.remove()
        except Exception:
            pass

        # Pull image if needed
        try:
            docker_client.images.get(config.image)
        except Exception:
            print(f"\nPulling {config.image}...")
            docker_client.images.pull(config.image)

        # Special handling for CockroachDB (needs start-single-node command)
        if config.db_type == "cockroachdb":
            container = docker_client.containers.run(
                config.image,
                name=container_name,
                command="start-single-node --insecure",
                environment=config.env_vars,
                ports={f"{config.internal_port}/tcp": None},  # Random host port
                detach=True,
            )
        else:
            container = docker_client.containers.run(
                config.image,
                name=container_name,
                environment=config.env_vars,
                ports={f"{config.internal_port}/tcp": None},  # Random host port
                detach=True,
            )

        # Wait for startup
        time.sleep(config.startup_time)

        yield container, config

        # Cleanup
        try:
            container.stop(timeout=5)
            container.remove()
        except Exception:
            pass

    @pytest.mark.parametrize(
        "container",
        DATABASE_CONFIGS,
        ids=[c.name for c in DATABASE_CONFIGS],
        indirect=True,
    )
    def test_database_detection(self, container):
        """Test that database container is correctly detected."""
        from sqlit.domains.connections.discovery.docker_detector import detect_database_containers

        container_obj, config = container

        status, detected = detect_database_containers()

        # Find our test container
        test_container = next(
            (c for c in detected if c.container_name == f"sqlit-test-{config.name}"),
            None,
        )

        assert test_container is not None, (
            f"Container 'sqlit-test-{config.name}' not detected. "
            f"Found: {[c.container_name for c in detected]}"
        )

        # Verify detected properties
        assert test_container.db_type == config.db_type, (
            f"Expected db_type '{config.db_type}', got '{test_container.db_type}'"
        )
        assert test_container.host == "localhost"
        assert test_container.port is not None, "Port should be detected"
        assert test_container.connectable is True

        # Verify credentials
        assert test_container.username == config.expected_user, (
            f"Expected user '{config.expected_user}', got '{test_container.username}'"
        )
        assert test_container.password == config.expected_password, (
            f"Expected password '{config.expected_password}', got '{test_container.password}'"
        )
        assert test_container.database == config.expected_database, (
            f"Expected database '{config.expected_database}', got '{test_container.database}'"
        )

    @pytest.mark.parametrize(
        "container",
        DATABASE_CONFIGS,
        ids=[c.name for c in DATABASE_CONFIGS],
        indirect=True,
    )
    def test_connection_config_conversion(self, container):
        """Test that detected container converts to valid ConnectionConfig."""
        from sqlit.domains.connections.discovery.docker_detector import (
            container_to_connection_config,
            detect_database_containers,
        )

        container_obj, config = container

        _, detected = detect_database_containers()
        test_container = next(
            (c for c in detected if c.container_name == f"sqlit-test-{config.name}"),
            None,
        )

        assert test_container is not None

        # Convert to ConnectionConfig
        conn_config = container_to_connection_config(test_container)

        # Verify ConnectionConfig properties
        assert conn_config.name == f"sqlit-test-{config.name}"
        assert conn_config.db_type == config.db_type
        if config.db_type == "turso":
            assert conn_config.server.startswith("http://localhost:")
        else:
            assert conn_config.server == "localhost"
        if config.db_type == "turso":
            assert conn_config.port == ""
            assert conn_config.server.startswith("http://")
        else:
            assert conn_config.port  # Should have a port string
            assert int(conn_config.port) > 0  # Should be a valid port number


class TestEdgeCases:
    """Test edge cases in container detection."""

    @pytest.fixture
    def docker_client(self):
        """Get Docker client."""
        import docker

        return docker.from_env()

    def test_container_without_port_mapping(self, docker_client, request):
        """Test handling of container without exposed ports."""
        if not request.config.getoption("--run-docker-container", default=False):
            pytest.skip("Use --run-docker-container to run container tests")

        from sqlit.domains.connections.discovery.docker_detector import detect_database_containers

        container_name = "sqlit-test-no-ports"

        # Cleanup
        try:
            existing = docker_client.containers.get(container_name)
            existing.stop(timeout=5)
            existing.remove()
        except Exception:
            pass

        # Run container WITHOUT port mapping
        container = docker_client.containers.run(
            "postgres:15-alpine",
            name=container_name,
            environment={"POSTGRES_PASSWORD": "testpass"},
            # No ports= argument - not exposed to host
            detach=True,
        )

        try:
            time.sleep(3)

            _, detected = detect_database_containers()
            test_container = next(
                (c for c in detected if c.container_name == container_name),
                None,
            )

            # Container should be detected but port should be None
            assert test_container is not None
            assert test_container.port is None, "Port should be None when not mapped"
            assert test_container.connectable is False
            assert test_container.db_type == "postgresql"
            assert test_container.password == "testpass"

        finally:
            container.stop(timeout=5)
            container.remove()

    def test_multiple_containers_same_type(self, docker_client, request):
        """Test detection of multiple containers of the same database type."""
        if not request.config.getoption("--run-docker-container", default=False):
            pytest.skip("Use --run-docker-container to run container tests")

        from sqlit.domains.connections.discovery.docker_detector import detect_database_containers

        containers = []
        container_names = ["sqlit-test-pg1", "sqlit-test-pg2", "sqlit-test-pg3"]

        try:
            # Create multiple PostgreSQL containers
            for i, name in enumerate(container_names):
                # Cleanup existing
                try:
                    existing = docker_client.containers.get(name)
                    existing.stop(timeout=5)
                    existing.remove()
                except Exception:
                    pass

                container = docker_client.containers.run(
                    "postgres:15-alpine",
                    name=name,
                    environment={
                        "POSTGRES_PASSWORD": f"pass{i}",
                        "POSTGRES_DB": f"db{i}",
                    },
                    ports={"5432/tcp": None},
                    detach=True,
                )
                containers.append(container)

            time.sleep(5)

            _, detected = detect_database_containers()

            # All three should be detected
            detected_names = {c.container_name for c in detected}
            for name in container_names:
                assert name in detected_names, f"Container {name} not detected"

            # Each should have unique credentials
            test_containers = [c for c in detected if c.container_name in container_names]
            passwords = {c.password for c in test_containers}
            databases = {c.database for c in test_containers}

            assert len(passwords) == 3, "Each container should have unique password"
            assert len(databases) == 3, "Each container should have unique database"

        finally:
            for container in containers:
                try:
                    container.stop(timeout=5)
                    container.remove()
                except Exception:
                    pass
