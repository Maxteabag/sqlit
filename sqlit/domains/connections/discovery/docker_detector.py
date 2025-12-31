"""Docker container auto-detection for database connections.

This module provides functionality to detect running database containers
and extract connection details from them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


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
    connectable: bool | None = None

    @property
    def is_running(self) -> bool:
        """Check if the container is running."""
        return self.status == ContainerStatus.RUNNING

    def __post_init__(self) -> None:
        if self.connectable is None:
            self.connectable = self.is_running and self.port is not None

    def get_display_name(self) -> str:
        """Get a display name for the container."""
        from sqlit.domains.connections.providers.metadata import get_display_name

        label = get_display_name(self.db_type)
        if label == self.db_type:
            label = self.db_type.upper()
        return f"{self.container_name} ({label})"


def _iter_docker_detectors() -> list[tuple[str, Any]]:
    from sqlit.domains.connections.providers.catalog import get_provider, get_supported_db_types

    detectors: list[tuple[str, Any]] = []
    for db_type in get_supported_db_types():
        provider = get_provider(db_type)
        if provider.docker_detector is None:
            continue
        detectors.append((db_type, provider.docker_detector))
    return detectors


def get_docker_status() -> DockerStatus:
    """Check if Docker is available and running.

    Returns:
        DockerStatus indicating the current state of Docker.
    """
    try:
        import docker  # pyright: ignore[reportMissingModuleSource]
    except ImportError:
        return DockerStatus.NOT_INSTALLED

    try:
        client = docker.from_env()
        client.ping()
        return DockerStatus.AVAILABLE
    except Exception as e:
        error_str = str(e).lower()
        if "permission denied" in error_str:
            return DockerStatus.NOT_ACCESSIBLE
        if "connection refused" in error_str or "connect" in error_str:
            return DockerStatus.NOT_RUNNING
        return DockerStatus.NOT_RUNNING


def _get_db_type_from_image(image_name: str) -> str | None:
    """Determine database type from Docker image name.

    Args:
        image_name: The Docker image name (e.g., 'postgres:15', 'mysql/mysql-server:8.0')

    Returns:
        Database type string or None if not a recognized database image.
    """
    for db_type, detector in _iter_docker_detectors():
        if detector.match_image(image_name):
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
    ports = container.attrs.get("NetworkSettings", {}).get("Ports") or {}

    # Try TCP port first
    port_key = f"{container_port}/tcp"
    bindings = ports.get(port_key)

    if bindings and len(bindings) > 0:
        host_port = bindings[0].get("HostPort")
        if host_port:
            return int(host_port)

    return None


def _get_single_mapped_host_port(container: Any) -> int | None:
    """Return a host port when only one TCP port mapping exists."""
    ports = container.attrs.get("NetworkSettings", {}).get("Ports") or {}
    mapped_ports: set[int] = set()
    for port_key, bindings in ports.items():
        if not port_key.endswith("/tcp") or not bindings:
            continue
        for binding in bindings:
            host_port = binding.get("HostPort")
            if host_port:
                mapped_ports.add(int(host_port))
    if len(mapped_ports) == 1:
        return mapped_ports.pop()
    return None


def _get_exposed_tcp_ports(container: Any) -> list[int]:
    """Return exposed TCP ports declared in the container config."""
    exposed = container.attrs.get("Config", {}).get("ExposedPorts") or {}
    exposed_ports = []
    for port_key in exposed.keys():
        if not port_key.endswith("/tcp"):
            continue
        port_str = port_key.split("/")[0]
        if port_str.isdigit():
            exposed_ports.append(int(port_str))
    return exposed_ports


def _get_container_image_name(container: Any) -> str | None:
    """Best-effort image name for tagless or digest-based images."""
    try:
        image_tags = container.image.tags
        if image_tags:
            return str(image_tags[0])
    except Exception:
        pass
    try:
        config_image = container.attrs.get("Config", {}).get("Image")
        if isinstance(config_image, str):
            return config_image
        if config_image:
            return str(config_image)
    except Exception:
        pass
    try:
        return str(container.image.short_id)
    except Exception:
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
        image_name = _get_container_image_name(container)
        if not image_name:
            continue

        # Determine database type
        db_type = _get_db_type_from_image(image_name)
        if not db_type:
            continue

        from sqlit.domains.connections.providers.catalog import get_provider

        provider = get_provider(db_type)
        detector = provider.docker_detector
        if detector is None:
            continue
        default_port_str = provider.metadata.default_port
        default_port = int(default_port_str) if default_port_str else None

        # Get host-mapped port (only available for running containers)
        host_port = None
        if container_status == ContainerStatus.RUNNING:
            if default_port:
                host_port = _get_host_port(container, default_port)
            if host_port is None:
                host_port = _get_single_mapped_host_port(container)

            network_mode = container.attrs.get("HostConfig", {}).get("NetworkMode")
            if host_port is None and network_mode == "host" and default_port:
                exposed_ports = _get_exposed_tcp_ports(container)
                if len(exposed_ports) == 1:
                    host_port = exposed_ports[0]
                else:
                    host_port = default_port

        # Get credentials from environment variables
        env_vars = _get_container_env_vars(container)
        credentials = detector.get_credentials(env_vars)

        # Create container name (strip leading slash if present)
        container_name = container.name
        if container_name.startswith("/"):
            container_name = container_name[1:]

        # Use 127.0.0.1 for MySQL/MariaDB to force TCP connection
        # (localhost causes them to try Unix socket which doesn't exist on host)
        host = detector.preferred_host

        # For databases that don't require auth, use empty string instead of None
        # This prevents the UI from prompting for a password
        password = credentials.password
        if password is None and not provider.metadata.requires_auth:
            password = ""

        detected.append(
            DetectedContainer(
                container_id=container.short_id,
                container_name=container_name,
                db_type=db_type,
                host=host,
                port=host_port,
                username=credentials.user,
                password=password,
                database=credentials.database,
                status=container_status,
                connectable=container_status == ContainerStatus.RUNNING and host_port is not None,
            )
        )

    return detected


def detect_database_containers(
    mock_containers: list[DetectedContainer] | None = None,
) -> tuple[DockerStatus, list[DetectedContainer]]:
    """Scan Docker containers for databases (running and exited).

    Returns:
        Tuple of (DockerStatus, list of DetectedContainer objects).
        Running containers are listed first, followed by exited containers.
    """
    # Check for explicit mock containers first
    if mock_containers is not None and mock_containers:
        # Sort: running first, then exited
        running = [c for c in mock_containers if c.status == ContainerStatus.RUNNING]
        exited = [c for c in mock_containers if c.status == ContainerStatus.EXITED]
        return DockerStatus.AVAILABLE, running + exited

    status = get_docker_status()
    if status != DockerStatus.AVAILABLE:
        return status, []

    try:
        import docker  # pyright: ignore[reportMissingModuleSource]

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
    from sqlit.domains.connections.domain.config import ConnectionConfig, TcpEndpoint
    from sqlit.domains.connections.providers.catalog import get_provider
    from sqlit.domains.connections.providers.config_service import normalize_connection_config

    server = container.host
    port = str(container.port) if container.port else ""
    provider = get_provider(container.db_type)
    config = ConnectionConfig(
        name=container.container_name,
        db_type=container.db_type,
        endpoint=TcpEndpoint(
            host=server,
            port=port or provider.metadata.default_port,
            database=container.database or "",
            username=container.username or "",
            password=container.password,
        ),
        source="docker",
    )
    normalize = getattr(provider.connection_factory, "normalize_docker_connection", None)
    if callable(normalize):
        config = cast(ConnectionConfig, normalize(config))
    return normalize_connection_config(config)
