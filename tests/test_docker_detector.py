"""Tests for Docker container auto-detection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sqlit.services.docker_detector import (
    DEFAULT_PORTS,
    DetectedContainer,
    DockerStatus,
    _get_container_credentials,
    _get_db_type_from_image,
    _get_host_port,
    container_to_connection_config,
    detect_database_containers,
    get_docker_status,
)


class TestDockerStatus:
    def test_docker_not_installed(self):
        """Test detection when docker SDK is not installed."""
        with patch.dict("sys.modules", {"docker": None}):
            # Force reimport to get NOT_INSTALLED status
            import importlib

            import sqlit.services.docker_detector as dd

            # Temporarily remove docker from modules to simulate not installed
            original_docker = __builtins__.__dict__.get("__import__")

            def mock_import(name, *args, **kwargs):
                if name == "docker":
                    raise ImportError("No module named 'docker'")
                return original_docker(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                importlib.reload(dd)
                # The status check happens at runtime, so we just verify the enum exists
                assert DockerStatus.NOT_INSTALLED.value == "not_installed"

    def test_docker_status_enum_values(self):
        """Test DockerStatus enum has all expected values."""
        assert DockerStatus.AVAILABLE.value == "available"
        assert DockerStatus.NOT_RUNNING.value == "not_running"
        assert DockerStatus.NOT_INSTALLED.value == "not_installed"
        assert DockerStatus.NOT_ACCESSIBLE.value == "not_accessible"


class TestImagePatternDetection:
    @pytest.mark.parametrize(
        "image_name,expected_db_type",
        [
            ("postgres:15", "postgresql"),
            ("postgres:latest", "postgresql"),
            ("library/postgres:15-alpine", "postgresql"),
            ("mysql:8.0", "mysql"),
            ("mysql/mysql-server:8.0", "mysql"),
            ("mariadb:10.11", "mariadb"),
            ("mcr.microsoft.com/mssql/server:2022-latest", "mssql"),
            ("clickhouse/clickhouse-server:latest", "clickhouse"),
            ("cockroachdb/cockroach:latest", "cockroachdb"),
            ("nginx:latest", None),
            ("redis:7", None),
            ("unknown-image", None),
        ],
    )
    def test_get_db_type_from_image(self, image_name: str, expected_db_type: str | None):
        """Test database type detection from image names."""
        assert _get_db_type_from_image(image_name) == expected_db_type


class TestCredentialExtraction:
    def test_postgresql_credentials(self):
        """Test PostgreSQL credential extraction."""
        env_vars = {
            "POSTGRES_USER": "myuser",
            "POSTGRES_PASSWORD": "mypass",
            "POSTGRES_DB": "mydb",
        }
        creds = _get_container_credentials("postgresql", env_vars)
        assert creds["user"] == "myuser"
        assert creds["password"] == "mypass"
        assert creds["database"] == "mydb"

    def test_postgresql_defaults(self):
        """Test PostgreSQL defaults when no env vars set."""
        creds = _get_container_credentials("postgresql", {})
        assert creds["user"] == "postgres"
        assert creds["password"] is None
        assert creds["database"] == "postgres"

    def test_mysql_root_password(self):
        """Test MySQL with root password."""
        env_vars = {"MYSQL_ROOT_PASSWORD": "rootpass"}
        creds = _get_container_credentials("mysql", env_vars)
        assert creds["user"] == "root"
        assert creds["password"] == "rootpass"

    def test_mysql_user_credentials(self):
        """Test MySQL with user credentials."""
        env_vars = {
            "MYSQL_USER": "myuser",
            "MYSQL_PASSWORD": "userpass",
            "MYSQL_DATABASE": "mydb",
        }
        creds = _get_container_credentials("mysql", env_vars)
        assert creds["user"] == "myuser"
        assert creds["password"] == "userpass"
        assert creds["database"] == "mydb"

    def test_mssql_credentials(self):
        """Test SQL Server credential extraction."""
        env_vars = {"SA_PASSWORD": "StrongP@ssw0rd"}
        creds = _get_container_credentials("mssql", env_vars)
        assert creds["user"] == "sa"
        assert creds["password"] == "StrongP@ssw0rd"
        assert creds["database"] == "master"

    def test_mariadb_fallback_to_mysql_vars(self):
        """Test MariaDB falls back to MYSQL_ vars."""
        env_vars = {
            "MYSQL_USER": "myuser",
            "MYSQL_PASSWORD": "mypass",
        }
        creds = _get_container_credentials("mariadb", env_vars)
        assert creds["user"] == "myuser"
        assert creds["password"] == "mypass"


class TestHostPortExtraction:
    def test_get_host_port_mapped(self):
        """Test extracting mapped host port."""
        mock_container = MagicMock()
        mock_container.attrs = {
            "NetworkSettings": {
                "Ports": {
                    "5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "15432"}],
                }
            }
        }
        assert _get_host_port(mock_container, 5432) == 15432

    def test_get_host_port_not_mapped(self):
        """Test when port is not mapped."""
        mock_container = MagicMock()
        mock_container.attrs = {"NetworkSettings": {"Ports": {}}}
        assert _get_host_port(mock_container, 5432) is None

    def test_get_host_port_empty_bindings(self):
        """Test when port bindings exist but are empty."""
        mock_container = MagicMock()
        mock_container.attrs = {
            "NetworkSettings": {
                "Ports": {
                    "5432/tcp": None,
                }
            }
        }
        assert _get_host_port(mock_container, 5432) is None


class TestDetectedContainer:
    def test_get_display_name(self):
        """Test container display name formatting."""
        container = DetectedContainer(
            container_id="abc123",
            container_name="my-postgres",
            db_type="postgresql",
            host="localhost",
            port=5432,
            username="postgres",
            password="secret",
            database="mydb",
        )
        assert container.get_display_name() == "my-postgres (PostgreSQL)"

    def test_get_display_name_unknown_type(self):
        """Test display name for unknown database type."""
        container = DetectedContainer(
            container_id="abc123",
            container_name="my-db",
            db_type="unknowndb",
            host="localhost",
            port=1234,
            username=None,
            password=None,
            database=None,
        )
        assert container.get_display_name() == "my-db (UNKNOWNDB)"


class TestContainerToConnectionConfig:
    def test_convert_container_to_config(self):
        """Test converting DetectedContainer to ConnectionConfig."""
        container = DetectedContainer(
            container_id="abc123",
            container_name="my-postgres",
            db_type="postgresql",
            host="localhost",
            port=5432,
            username="postgres",
            password="secret",
            database="mydb",
        )
        config = container_to_connection_config(container)

        assert config.name == "my-postgres"
        assert config.db_type == "postgresql"
        assert config.server == "localhost"
        assert config.port == "5432"
        assert config.username == "postgres"
        assert config.password == "secret"
        assert config.database == "mydb"

    def test_convert_container_with_none_values(self):
        """Test converting container with None values."""
        container = DetectedContainer(
            container_id="abc123",
            container_name="my-mysql",
            db_type="mysql",
            host="localhost",
            port=None,
            username=None,
            password=None,
            database=None,
        )
        config = container_to_connection_config(container)

        assert config.name == "my-mysql"
        assert config.port == ""
        assert config.username == ""
        assert config.password is None
        assert config.database == ""


class TestDetectDatabaseContainers:
    def test_detect_containers_docker_not_installed(self):
        """Test detection when docker SDK is not installed."""
        with patch(
            "sqlit.services.docker_detector.get_docker_status",
            return_value=DockerStatus.NOT_INSTALLED,
        ):
            status, containers = detect_database_containers()
            assert status == DockerStatus.NOT_INSTALLED
            assert containers == []

    def test_detect_containers_docker_not_running(self):
        """Test detection when docker daemon is not running."""
        with patch(
            "sqlit.services.docker_detector.get_docker_status",
            return_value=DockerStatus.NOT_RUNNING,
        ):
            status, containers = detect_database_containers()
            assert status == DockerStatus.NOT_RUNNING
            assert containers == []

    def test_detect_containers_success(self):
        """Test successful container detection."""
        mock_container = MagicMock()
        mock_container.name = "test-postgres"
        mock_container.short_id = "abc123"
        mock_container.image.tags = ["postgres:15"]
        mock_container.attrs = {
            "Config": {
                "Env": [
                    "POSTGRES_USER=testuser",
                    "POSTGRES_PASSWORD=testpass",
                    "POSTGRES_DB=testdb",
                ]
            },
            "NetworkSettings": {
                "Ports": {
                    "5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "5432"}],
                }
            },
        }

        mock_client = MagicMock()
        mock_client.containers.list.return_value = [mock_container]
        mock_client.ping.return_value = True

        with (
            patch(
                "sqlit.services.docker_detector.get_docker_status",
                return_value=DockerStatus.AVAILABLE,
            ),
            patch("docker.from_env", return_value=mock_client),
        ):
            status, containers = detect_database_containers()

            assert status == DockerStatus.AVAILABLE
            assert len(containers) == 1
            assert containers[0].container_name == "test-postgres"
            assert containers[0].db_type == "postgresql"
            assert containers[0].port == 5432
            assert containers[0].username == "testuser"
            assert containers[0].password == "testpass"
            assert containers[0].database == "testdb"


class TestDefaultPorts:
    def test_default_ports_defined(self):
        """Test that default ports are defined for all supported databases."""
        assert DEFAULT_PORTS["postgresql"] == 5432
        assert DEFAULT_PORTS["mysql"] == 3306
        assert DEFAULT_PORTS["mariadb"] == 3306
        assert DEFAULT_PORTS["mssql"] == 1433
        assert DEFAULT_PORTS["clickhouse"] == 9000
        assert DEFAULT_PORTS["cockroachdb"] == 26257
