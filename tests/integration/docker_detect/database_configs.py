"""Database container configurations for Docker detection tests."""

from __future__ import annotations

from dataclasses import dataclass


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
]
