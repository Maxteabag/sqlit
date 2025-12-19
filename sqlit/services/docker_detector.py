"""Docker container auto-detection for database connections.

This module provides functionality to detect running database containers
and extract connection details from them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..config import ConnectionConfig


class DockerStatus(Enum):
    """Status of Docker availability."""

    AVAILABLE = "available"
    NOT_RUNNING = "not_running"
    NOT_INSTALLED = "not_installed"
    NOT_ACCESSIBLE = "not_accessible"


class ContainerStatus(Enum):
    """Status of a Docker container."""

    RUNNING = "running"
    EXITED = "exited"


@dataclass
class DetectedContainer:
    """A detected database container with connection details."""

    container_id: str
    container_name: str
    db_type: str  # postgresql, mysql, mssql, etc.
    host: str
    port: int | None
    username: str | None
    password: str | None
    database: str | None
    status: ContainerStatus = ContainerStatus.RUNNING

    @property
    def is_running(self) -> bool:
        """Check if the container is running."""
        return self.status == ContainerStatus.RUNNING

    def get_display_name(self) -> str:
        """Get a display name for the container."""
        db_labels = {
            "postgresql": "PostgreSQL",
            "mysql": "MySQL",
            "mariadb": "MariaDB",
            "mssql": "SQL Server",
            "clickhouse": "ClickHouse",
            "cockroachdb": "CockroachDB",
        }
        label = db_labels.get(self.db_type, self.db_type.upper())
        return f"{self.container_name} ({label})"


# Image patterns to database type mapping
IMAGE_PATTERNS: dict[str, str] = {
    "postgres": "postgresql",
    "mysql": "mysql",
    "mariadb": "mariadb",
    "mcr.microsoft.com/mssql": "mssql",
    "mcr.microsoft.com/azure-sql-edge": "mssql",  # ARM64-compatible SQL Server
    "clickhouse": "clickhouse",
    "cockroachdb": "cockroachdb",
}

# Environment variable mappings for credential extraction
CREDENTIAL_ENV_VARS: dict[str, dict[str, str | list[str]]] = {
    "postgresql": {
        "user": ["POSTGRES_USER"],
        "password": ["POSTGRES_PASSWORD"],
        "database": ["POSTGRES_DB"],
        "default_user": "postgres",
        "default_database": "postgres",
    },
    "mysql": {
        "user": ["MYSQL_USER"],
        "password": ["MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD"],
        "database": ["MYSQL_DATABASE"],
        "default_user": "root",
        "default_database": "",
    },
    "mariadb": {
        "user": ["MARIADB_USER", "MYSQL_USER"],
        "password": ["MARIADB_PASSWORD", "MARIADB_ROOT_PASSWORD", "MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD"],
        "database": ["MARIADB_DATABASE", "MYSQL_DATABASE"],
        "default_user": "root",
        "default_database": "",
    },
    "mssql": {
        "user": [],  # Always 'sa' for SQL Server
        "password": ["SA_PASSWORD", "MSSQL_SA_PASSWORD"],
        "database": [],
        "default_user": "sa",
        "default_database": "master",
    },
    "clickhouse": {
        "user": ["CLICKHOUSE_USER"],
        "password": ["CLICKHOUSE_PASSWORD"],
        "database": ["CLICKHOUSE_DB", "CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT"],
        "default_user": "default",
        "default_database": "default",
    },
    "cockroachdb": {
        "user": ["COCKROACH_USER"],
        "password": ["COCKROACH_PASSWORD"],
        "database": ["COCKROACH_DATABASE"],
        "default_user": "root",
        "default_database": "defaultdb",
    },
}

# Default ports for database types
DEFAULT_PORTS: dict[str, int] = {
    "postgresql": 5432,
    "mysql": 3306,
    "mariadb": 3306,
    "mssql": 1433,
    "clickhouse": 9000,
    "cockroachdb": 26257,
}


def get_docker_status() -> DockerStatus:
    """Check if Docker is available and running.

    Returns:
        DockerStatus indicating the current state of Docker.
    """
    try:
        import docker
    except ImportError:
        return DockerStatus.NOT_INSTALLED

    try:
        client = docker.from_env()
        client.ping()
        return DockerStatus.AVAILABLE
    except docker.errors.DockerException as e:
        error_str = str(e).lower()
        if "permission denied" in error_str:
            return DockerStatus.NOT_ACCESSIBLE
        if "connection refused" in error_str or "connect" in error_str:
            return DockerStatus.NOT_RUNNING
        return DockerStatus.NOT_RUNNING
    except Exception:
        return DockerStatus.NOT_RUNNING


def _get_db_type_from_image(image_name: str) -> str | None:
    """Determine database type from Docker image name.

    Args:
        image_name: The Docker image name (e.g., 'postgres:15', 'mysql/mysql-server:8.0')

    Returns:
        Database type string or None if not a recognized database image.
    """
    image_lower = image_name.lower()
    for pattern, db_type in IMAGE_PATTERNS.items():
        if pattern in image_lower:
            return db_type
    return None


def _get_host_port(container: Any, container_port: int) -> int | None:
    """Extract the host-mapped port from container port bindings.

    Args:
        container: Docker container object
        container_port: The container's internal port

    Returns:
        Host port number or None if not mapped.
    """
    ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})

    # Try TCP port first
    port_key = f"{container_port}/tcp"
    bindings = ports.get(port_key)

    if bindings and len(bindings) > 0:
        host_port = bindings[0].get("HostPort")
        if host_port:
            return int(host_port)

    return None


def _get_container_env_vars(container: Any) -> dict[str, str]:
    """Extract environment variables from a container.

    Args:
        container: Docker container object

    Returns:
        Dictionary of environment variable name to value.
    """
    env_list = container.attrs.get("Config", {}).get("Env", [])
    env_dict = {}
    for env in env_list:
        if "=" in env:
            key, value = env.split("=", 1)
            env_dict[key] = value
    return env_dict


def _get_container_credentials(db_type: str, env_vars: dict[str, str]) -> dict[str, str | None]:
    """Extract credentials from container environment variables.

    Args:
        db_type: The database type (postgresql, mysql, etc.)
        env_vars: Container environment variables

    Returns:
        Dictionary with user, password, and database keys.
    """
    config = CREDENTIAL_ENV_VARS.get(db_type, {})

    def get_first_matching(var_names: list[str]) -> str | None:
        for var_name in var_names:
            if var_name in env_vars:
                return env_vars[var_name]
        return None

    user_vars = config.get("user", [])
    password_vars = config.get("password", [])
    database_vars = config.get("database", [])

    user = get_first_matching(user_vars) if isinstance(user_vars, list) else None
    password = get_first_matching(password_vars) if isinstance(password_vars, list) else None
    database = get_first_matching(database_vars) if isinstance(database_vars, list) else None

    # Apply defaults
    if not user:
        user = config.get("default_user")
    if not database:
        database = config.get("default_database")

    # Special case: MySQL/MariaDB with root password but no user
    if db_type in ("mysql", "mariadb") and not user and password:
        user = "root"

    return {
        "user": user,
        "password": password,
        "database": database,
    }


def _detect_containers_with_status(
    client: Any, status_filter: str, container_status: ContainerStatus
) -> list[DetectedContainer]:
    """Detect database containers with a specific status.

    Args:
        client: Docker client
        status_filter: Docker status filter (e.g., "running", "exited")
        container_status: ContainerStatus to assign to detected containers

    Returns:
        List of DetectedContainer objects
    """
    try:
        containers = client.containers.list(filters={"status": status_filter})
    except Exception:
        return []

    detected: list[DetectedContainer] = []

    for container in containers:
        # Get image name
        try:
            image_tags = container.image.tags
            image_name = image_tags[0] if image_tags else container.image.short_id
        except Exception:
            continue

        # Determine database type
        db_type = _get_db_type_from_image(image_name)
        if not db_type:
            continue

        # Get the default port for this database type
        default_port = DEFAULT_PORTS.get(db_type)
        if not default_port:
            continue

        # Get host-mapped port (only available for running containers)
        host_port = _get_host_port(container, default_port) if container_status == ContainerStatus.RUNNING else None

        # Get credentials from environment variables
        env_vars = _get_container_env_vars(container)
        credentials = _get_container_credentials(db_type, env_vars)

        # Create container name (strip leading slash if present)
        container_name = container.name
        if container_name.startswith("/"):
            container_name = container_name[1:]

        detected.append(
            DetectedContainer(
                container_id=container.short_id,
                container_name=container_name,
                db_type=db_type,
                host="localhost",
                port=host_port,
                username=credentials.get("user"),
                password=credentials.get("password"),
                database=credentials.get("database"),
                status=container_status,
            )
        )

    return detected


def detect_database_containers() -> tuple[DockerStatus, list[DetectedContainer]]:
    """Scan Docker containers for databases (running and exited).

    Returns:
        Tuple of (DockerStatus, list of DetectedContainer objects).
        Running containers are listed first, followed by exited containers.
    """
    # Check for mock containers first
    from ..mock_settings import get_mock_docker_containers

    mock_containers = get_mock_docker_containers()
    if mock_containers is not None:
        # Sort: running first, then exited
        running = [c for c in mock_containers if c.status == ContainerStatus.RUNNING]
        exited = [c for c in mock_containers if c.status == ContainerStatus.EXITED]
        return DockerStatus.AVAILABLE, running + exited

    status = get_docker_status()
    if status != DockerStatus.AVAILABLE:
        return status, []

    try:
        import docker

        client = docker.from_env()
    except Exception:
        return DockerStatus.NOT_ACCESSIBLE, []

    # Detect running containers first
    running = _detect_containers_with_status(client, "running", ContainerStatus.RUNNING)

    # Detect exited containers
    exited = _detect_containers_with_status(client, "exited", ContainerStatus.EXITED)

    # Return running first, then exited
    return DockerStatus.AVAILABLE, running + exited


def container_to_connection_config(container: DetectedContainer) -> ConnectionConfig:
    """Convert a DetectedContainer to a ConnectionConfig.

    Args:
        container: The detected container

    Returns:
        ConnectionConfig ready for connection or saving.
    """
    from ..config import ConnectionConfig

    return ConnectionConfig(
        name=container.container_name,
        db_type=container.db_type,
        server=container.host,
        port=str(container.port) if container.port else "",
        database=container.database or "",
        username=container.username or "",
        password=container.password,
        source="docker",
    )
