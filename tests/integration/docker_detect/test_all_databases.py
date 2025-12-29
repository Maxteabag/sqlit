"""Integration tests for Docker detection across all supported database types.

These tests spin up real database containers and verify detection works correctly.
They are slow and require Docker, so they're opt-in via --run-docker-container flag.

To run:
    pytest tests/integration/docker_detect/test_all_databases.py -v --run-docker-container
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass


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


@dataclass
class DatabaseTestConfig:
    """Configuration for testing a database container."""

    name: str  # Test name
    image: str  # Docker image
    db_type: str  # Expected detected db_type
    env_vars: dict[str, str]  # Environment variables
    internal_port: int  # Container's internal port
    expected_user: str | None  # Expected detected username
    expected_password: str | None  # Expected detected password
    expected_database: str | None  # Expected detected database
    startup_time: int = 5  # Seconds to wait for container startup


# Test configurations for each database type
DATABASE_CONFIGS = [
    # PostgreSQL - standard config
    DatabaseTestConfig(
        name="postgres_standard",
        image="postgres:15-alpine",
        db_type="postgresql",
        env_vars={
            "POSTGRES_USER": "testuser",
            "POSTGRES_PASSWORD": "testpass",
            "POSTGRES_DB": "testdb",
        },
        internal_port=5432,
        expected_user="testuser",
        expected_password="testpass",
        expected_database="testdb",
        startup_time=3,
    ),
    # PostgreSQL - minimal config (password only)
    DatabaseTestConfig(
        name="postgres_minimal",
        image="postgres:16-alpine",
        db_type="postgresql",
        env_vars={"POSTGRES_PASSWORD": "secretpass"},
        internal_port=5432,
        expected_user="postgres",  # Default
        expected_password="secretpass",
        expected_database=None,  # No default_database anymore
        startup_time=3,
    ),
    # MySQL - root password only
    DatabaseTestConfig(
        name="mysql_root",
        image="mysql:8.0",
        db_type="mysql",
        env_vars={"MYSQL_ROOT_PASSWORD": "rootpass"},
        internal_port=3306,
        expected_user="root",
        expected_password="rootpass",
        expected_database="",
        startup_time=15,  # MySQL takes longer to start
    ),
    # MySQL - with user
    DatabaseTestConfig(
        name="mysql_user",
        image="mysql:8.4",
        db_type="mysql",
        env_vars={
            "MYSQL_ROOT_PASSWORD": "rootpass",
            "MYSQL_USER": "appuser",
            "MYSQL_PASSWORD": "apppass",
            "MYSQL_DATABASE": "appdb",
        },
        internal_port=3306,
        expected_user="appuser",
        expected_password="apppass",
        expected_database="appdb",
        startup_time=15,
    ),
    # MariaDB - with MariaDB-specific vars
    DatabaseTestConfig(
        name="mariadb_native",
        image="mariadb:11",
        db_type="mariadb",
        env_vars={
            "MARIADB_USER": "mariauser",
            "MARIADB_PASSWORD": "mariapass",
            "MARIADB_DATABASE": "mariadb",
            "MARIADB_ROOT_PASSWORD": "rootpass",
        },
        internal_port=3306,
        expected_user="mariauser",
        expected_password="mariapass",
        expected_database="mariadb",
        startup_time=10,
    ),
    # MariaDB - with MySQL-compatible vars
    DatabaseTestConfig(
        name="mariadb_mysql_compat",
        image="mariadb:10.11",
        db_type="mariadb",
        env_vars={
            "MYSQL_USER": "mysqluser",
            "MYSQL_PASSWORD": "mysqlpass",
            "MYSQL_DATABASE": "mysqldb",
            "MYSQL_ROOT_PASSWORD": "rootpass",
        },
        internal_port=3306,
        expected_user="mysqluser",
        expected_password="mysqlpass",
        expected_database="mysqldb",
        startup_time=10,
    ),
    # SQL Server 2022
    DatabaseTestConfig(
        name="mssql_2022",
        image="mcr.microsoft.com/mssql/server:2022-latest",
        db_type="mssql",
        env_vars={
            "ACCEPT_EULA": "Y",
            "SA_PASSWORD": "StrongP@ss123!",
        },
        internal_port=1433,
        expected_user="sa",
        expected_password="StrongP@ss123!",
        expected_database=None,  # No default_database anymore
        startup_time=15,
    ),
    # SQL Server with MSSQL_SA_PASSWORD
    DatabaseTestConfig(
        name="mssql_alt_env",
        image="mcr.microsoft.com/mssql/server:2019-latest",
        db_type="mssql",
        env_vars={
            "ACCEPT_EULA": "Y",
            "MSSQL_SA_PASSWORD": "AltP@ssword456!",
        },
        internal_port=1433,
        expected_user="sa",
        expected_password="AltP@ssword456!",
        expected_database=None,  # No default_database anymore
        startup_time=15,
    ),
    # ClickHouse
    DatabaseTestConfig(
        name="clickhouse_standard",
        image="clickhouse/clickhouse-server:latest",
        db_type="clickhouse",
        env_vars={
            "CLICKHOUSE_USER": "chuser",
            "CLICKHOUSE_PASSWORD": "chpass",
            "CLICKHOUSE_DB": "chdb",
        },
        internal_port=8123,  # HTTP interface port
        expected_user="chuser",
        expected_password="chpass",
        expected_database="chdb",
        startup_time=5,
    ),
    # ClickHouse - default config
    DatabaseTestConfig(
        name="clickhouse_default",
        image="clickhouse/clickhouse-server:23.8",
        db_type="clickhouse",
        env_vars={},
        internal_port=8123,  # HTTP interface port
        expected_user="default",
        expected_password=None,
        expected_database=None,  # No default_database anymore
        startup_time=5,
    ),
    # CockroachDB
    DatabaseTestConfig(
        name="cockroachdb_insecure",
        image="cockroachdb/cockroach:latest",
        db_type="cockroachdb",
        env_vars={},
        internal_port=26257,
        expected_user="root",
        expected_password=None,
        expected_database=None,  # No default_database anymore
        startup_time=10,
    ),
    # Oracle Free
    DatabaseTestConfig(
        name="oracle_free",
        image="gvenzl/oracle-free:23-slim",
        db_type="oracle",
        env_vars={
            "ORACLE_PASSWORD": "OraclePass123!",
            "APP_USER": "appuser",
            "APP_USER_PASSWORD": "apppass",
        },
        internal_port=1521,
        expected_user="appuser",
        expected_password="apppass",
        expected_database="FREEPDB1",
        startup_time=60,
    ),
    # Turso (libSQL server)
    DatabaseTestConfig(
        name="turso_libsql",
        image="ghcr.io/tursodatabase/libsql-server:latest",
        db_type="turso",
        env_vars={},
        internal_port=8080,
        expected_user="",
        expected_password=None,
        expected_database="",
        startup_time=5,
    ),
    # Flight SQL (using voltrondata/sqlflite)
    DatabaseTestConfig(
        name="flight_sqlflite",
        image="voltrondata/sqlflite:latest",
        db_type="flight",
        env_vars={
            "TLS_ENABLED": "0",
            "SQLFLITE_PASSWORD": "test_password",
        },
        internal_port=31337,
        expected_user="",
        expected_password="test_password",
        expected_database=None,
        startup_time=5,
    ),
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
        from sqlit.services.docker_detector import detect_database_containers

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
        from sqlit.services.docker_detector import (
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

        from sqlit.services.docker_detector import detect_database_containers

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

        from sqlit.services.docker_detector import detect_database_containers

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
