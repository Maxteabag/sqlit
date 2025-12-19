"""Unit tests for Docker credential extraction logic.

These tests verify the credential parsing logic without requiring Docker.
They test edge cases and variations in how databases configure credentials.
"""

from __future__ import annotations

import pytest

from sqlit.services.docker_detector import (
    _get_container_credentials,
    _get_db_type_from_image,
)


class TestImagePatternMatching:
    """Test database type detection from image names."""

    @pytest.mark.parametrize(
        "image_name,expected",
        [
            # PostgreSQL variations
            ("postgres", "postgresql"),
            ("postgres:latest", "postgresql"),
            ("postgres:15", "postgresql"),
            ("postgres:15-alpine", "postgresql"),
            ("postgres:15-bullseye", "postgresql"),
            ("postgres:16.1-alpine3.18", "postgresql"),
            ("library/postgres:15", "postgresql"),
            ("docker.io/library/postgres:15", "postgresql"),
            # Custom registries
            ("gcr.io/my-project/postgres:15", "postgresql"),
            ("myregistry.azurecr.io/postgres:latest", "postgresql"),
            ("123456789.dkr.ecr.us-east-1.amazonaws.com/postgres:15", "postgresql"),
            # MySQL variations
            ("mysql", "mysql"),
            ("mysql:8.0", "mysql"),
            ("mysql:8.4", "mysql"),
            ("mysql:5.7", "mysql"),
            ("mysql/mysql-server:8.0", "mysql"),
            ("mysql/mysql-server:8.0-aarch64", "mysql"),
            # MariaDB variations
            ("mariadb", "mariadb"),
            ("mariadb:10.11", "mariadb"),
            ("mariadb:11.2", "mariadb"),
            ("mariadb:lts", "mariadb"),
            # SQL Server variations
            ("mcr.microsoft.com/mssql/server", "mssql"),
            ("mcr.microsoft.com/mssql/server:2017-latest", "mssql"),
            ("mcr.microsoft.com/mssql/server:2019-latest", "mssql"),
            ("mcr.microsoft.com/mssql/server:2022-latest", "mssql"),
            ("mcr.microsoft.com/mssql/server:2022-CU10-ubuntu-22.04", "mssql"),
            # Azure SQL Edge (ARM64 compatible)
            ("mcr.microsoft.com/azure-sql-edge", "mssql"),
            ("mcr.microsoft.com/azure-sql-edge:latest", "mssql"),
            # ClickHouse variations
            ("clickhouse/clickhouse-server", "clickhouse"),
            ("clickhouse/clickhouse-server:latest", "clickhouse"),
            ("clickhouse/clickhouse-server:23.8", "clickhouse"),
            ("yandex/clickhouse-server:latest", "clickhouse"),  # Old image name
            # CockroachDB variations
            ("cockroachdb/cockroach", "cockroachdb"),
            ("cockroachdb/cockroach:latest", "cockroachdb"),
            ("cockroachdb/cockroach:v23.1.0", "cockroachdb"),
            # Non-database images (should return None)
            ("nginx", None),
            ("nginx:latest", None),
            ("redis:7", None),
            ("ubuntu:22.04", None),
            ("python:3.11", None),
            ("node:18", None),
            # Tricky names that shouldn't match
            ("my-postgres-app", "postgresql"),  # Contains 'postgres'
            ("mysql-backup-tool", "mysql"),  # Contains 'mysql'
        ],
    )
    def test_image_pattern_detection(self, image_name: str, expected: str | None):
        """Test that image names are correctly mapped to database types."""
        assert _get_db_type_from_image(image_name) == expected


class TestPostgreSQLCredentials:
    """Test PostgreSQL credential extraction."""

    def test_full_credentials(self):
        """Test with all credentials provided."""
        env = {
            "POSTGRES_USER": "myuser",
            "POSTGRES_PASSWORD": "mypass",
            "POSTGRES_DB": "mydb",
        }
        creds = _get_container_credentials("postgresql", env)
        assert creds["user"] == "myuser"
        assert creds["password"] == "mypass"
        assert creds["database"] == "mydb"

    def test_defaults_when_empty(self):
        """Test default values when no env vars set."""
        creds = _get_container_credentials("postgresql", {})
        assert creds["user"] == "postgres"
        assert creds["password"] is None
        assert creds["database"] == "postgres"

    def test_password_only(self):
        """Test with only password set (common minimal config)."""
        env = {"POSTGRES_PASSWORD": "secret"}
        creds = _get_container_credentials("postgresql", env)
        assert creds["user"] == "postgres"
        assert creds["password"] == "secret"
        assert creds["database"] == "postgres"

    def test_user_without_password(self):
        """Test custom user without password (trust auth)."""
        env = {"POSTGRES_USER": "devuser"}
        creds = _get_container_credentials("postgresql", env)
        assert creds["user"] == "devuser"
        assert creds["password"] is None

    def test_empty_password_string(self):
        """Test explicitly empty password."""
        env = {"POSTGRES_PASSWORD": ""}
        creds = _get_container_credentials("postgresql", env)
        assert creds["password"] == ""


class TestMySQLCredentials:
    """Test MySQL credential extraction with root/user variations."""

    def test_root_password_only(self):
        """Test MySQL with only root password (most common dev setup)."""
        env = {"MYSQL_ROOT_PASSWORD": "rootpass"}
        creds = _get_container_credentials("mysql", env)
        assert creds["user"] == "root"
        assert creds["password"] == "rootpass"

    def test_user_credentials(self):
        """Test MySQL with non-root user."""
        env = {
            "MYSQL_USER": "appuser",
            "MYSQL_PASSWORD": "apppass",
            "MYSQL_DATABASE": "appdb",
        }
        creds = _get_container_credentials("mysql", env)
        assert creds["user"] == "appuser"
        assert creds["password"] == "apppass"
        assert creds["database"] == "appdb"

    def test_user_takes_precedence_over_root(self):
        """Test that MYSQL_USER is preferred over root."""
        env = {
            "MYSQL_ROOT_PASSWORD": "rootpass",
            "MYSQL_USER": "appuser",
            "MYSQL_PASSWORD": "apppass",
        }
        creds = _get_container_credentials("mysql", env)
        assert creds["user"] == "appuser"
        assert creds["password"] == "apppass"

    def test_root_password_fallback(self):
        """Test fallback to root password when user password missing."""
        env = {
            "MYSQL_ROOT_PASSWORD": "rootpass",
            "MYSQL_USER": "appuser",
            # No MYSQL_PASSWORD
        }
        creds = _get_container_credentials("mysql", env)
        # User is set but no password, falls back to root password
        assert creds["user"] == "appuser"
        assert creds["password"] == "rootpass"

    def test_allow_empty_password(self):
        """Test MYSQL_ALLOW_EMPTY_PASSWORD scenario."""
        env = {"MYSQL_ALLOW_EMPTY_PASSWORD": "yes"}
        creds = _get_container_credentials("mysql", env)
        assert creds["user"] == "root"
        assert creds["password"] is None

    def test_random_root_password(self):
        """Test MYSQL_RANDOM_ROOT_PASSWORD (can't extract password)."""
        env = {"MYSQL_RANDOM_ROOT_PASSWORD": "yes"}
        creds = _get_container_credentials("mysql", env)
        assert creds["password"] is None


class TestMariaDBCredentials:
    """Test MariaDB credential extraction with both MARIADB_* and MYSQL_* vars."""

    def test_mariadb_vars(self):
        """Test native MariaDB environment variables."""
        env = {
            "MARIADB_USER": "mariauser",
            "MARIADB_PASSWORD": "mariapass",
            "MARIADB_DATABASE": "mariadb",
        }
        creds = _get_container_credentials("mariadb", env)
        assert creds["user"] == "mariauser"
        assert creds["password"] == "mariapass"
        assert creds["database"] == "mariadb"

    def test_mysql_vars_fallback(self):
        """Test fallback to MYSQL_* variables for compatibility."""
        env = {
            "MYSQL_USER": "mysqluser",
            "MYSQL_PASSWORD": "mysqlpass",
            "MYSQL_DATABASE": "mysqldb",
        }
        creds = _get_container_credentials("mariadb", env)
        assert creds["user"] == "mysqluser"
        assert creds["password"] == "mysqlpass"
        assert creds["database"] == "mysqldb"

    def test_mariadb_takes_precedence(self):
        """Test that MARIADB_* vars take precedence over MYSQL_*."""
        env = {
            "MARIADB_USER": "mariauser",
            "MYSQL_USER": "mysqluser",
            "MARIADB_PASSWORD": "mariapass",
        }
        creds = _get_container_credentials("mariadb", env)
        assert creds["user"] == "mariauser"

    def test_mariadb_root_password(self):
        """Test MariaDB root password variations."""
        env = {"MARIADB_ROOT_PASSWORD": "rootpass"}
        creds = _get_container_credentials("mariadb", env)
        assert creds["user"] == "root"
        assert creds["password"] == "rootpass"

    def test_mysql_root_password_fallback(self):
        """Test fallback to MYSQL_ROOT_PASSWORD."""
        env = {"MYSQL_ROOT_PASSWORD": "rootpass"}
        creds = _get_container_credentials("mariadb", env)
        assert creds["user"] == "root"
        assert creds["password"] == "rootpass"


class TestSQLServerCredentials:
    """Test SQL Server credential extraction."""

    def test_sa_password(self):
        """Test standard SA_PASSWORD."""
        env = {"SA_PASSWORD": "StrongP@ss123"}
        creds = _get_container_credentials("mssql", env)
        assert creds["user"] == "sa"
        assert creds["password"] == "StrongP@ss123"
        assert creds["database"] == "master"

    def test_mssql_sa_password(self):
        """Test alternative MSSQL_SA_PASSWORD."""
        env = {"MSSQL_SA_PASSWORD": "StrongP@ss123"}
        creds = _get_container_credentials("mssql", env)
        assert creds["user"] == "sa"
        assert creds["password"] == "StrongP@ss123"

    def test_sa_password_takes_precedence(self):
        """Test SA_PASSWORD takes precedence over MSSQL_SA_PASSWORD."""
        env = {
            "SA_PASSWORD": "primary",
            "MSSQL_SA_PASSWORD": "secondary",
        }
        creds = _get_container_credentials("mssql", env)
        assert creds["password"] == "primary"

    def test_accept_eula_only(self):
        """Test container with only ACCEPT_EULA (no password = can't connect)."""
        env = {"ACCEPT_EULA": "Y"}
        creds = _get_container_credentials("mssql", env)
        assert creds["user"] == "sa"
        assert creds["password"] is None


class TestClickHouseCredentials:
    """Test ClickHouse credential extraction."""

    def test_full_credentials(self):
        """Test with all credentials provided."""
        env = {
            "CLICKHOUSE_USER": "chuser",
            "CLICKHOUSE_PASSWORD": "chpass",
            "CLICKHOUSE_DB": "chdb",
        }
        creds = _get_container_credentials("clickhouse", env)
        assert creds["user"] == "chuser"
        assert creds["password"] == "chpass"
        assert creds["database"] == "chdb"

    def test_defaults(self):
        """Test ClickHouse defaults (default user, no password)."""
        creds = _get_container_credentials("clickhouse", {})
        assert creds["user"] == "default"
        assert creds["password"] is None
        assert creds["database"] == "default"

    def test_password_only(self):
        """Test with only password set."""
        env = {"CLICKHOUSE_PASSWORD": "secret"}
        creds = _get_container_credentials("clickhouse", env)
        assert creds["user"] == "default"
        assert creds["password"] == "secret"


class TestCockroachDBCredentials:
    """Test CockroachDB credential extraction."""

    def test_full_credentials(self):
        """Test with all credentials provided."""
        env = {
            "COCKROACH_USER": "crdbuser",
            "COCKROACH_PASSWORD": "crdbpass",
            "COCKROACH_DATABASE": "crdb",
        }
        creds = _get_container_credentials("cockroachdb", env)
        assert creds["user"] == "crdbuser"
        assert creds["password"] == "crdbpass"
        assert creds["database"] == "crdb"

    def test_defaults_insecure_mode(self):
        """Test CockroachDB defaults (often runs insecure in dev)."""
        creds = _get_container_credentials("cockroachdb", {})
        assert creds["user"] == "root"
        assert creds["password"] is None
        assert creds["database"] == "defaultdb"


class TestEdgeCases:
    """Test edge cases in credential extraction."""

    def test_env_vars_with_whitespace(self):
        """Test that whitespace in values is preserved."""
        env = {"POSTGRES_PASSWORD": "  pass with spaces  "}
        creds = _get_container_credentials("postgresql", env)
        assert creds["password"] == "  pass with spaces  "

    def test_env_vars_with_special_chars(self):
        """Test passwords with special characters."""
        env = {"POSTGRES_PASSWORD": "p@ss=word!#$%^&*()"}
        creds = _get_container_credentials("postgresql", env)
        assert creds["password"] == "p@ss=word!#$%^&*()"

    def test_unicode_password(self):
        """Test Unicode characters in password."""
        env = {"POSTGRES_PASSWORD": "密码123"}
        creds = _get_container_credentials("postgresql", env)
        assert creds["password"] == "密码123"

    def test_unknown_db_type(self):
        """Test graceful handling of unknown database type."""
        creds = _get_container_credentials("unknowndb", {"SOME_VAR": "value"})
        assert creds["user"] is None
        assert creds["password"] is None
        assert creds["database"] is None

    def test_case_sensitivity(self):
        """Test that env var names are case-sensitive."""
        env = {
            "postgres_password": "lowercase",  # Wrong case
            "POSTGRES_PASSWORD": "correct",
        }
        creds = _get_container_credentials("postgresql", env)
        assert creds["password"] == "correct"
