"""CLI command handlers for sqlit."""

from __future__ import annotations

import sys
from typing import Any

from sqlit.domains.connections.app.credentials import (
    ALLOW_PLAINTEXT_CREDENTIALS_SETTING,
    CredentialsPersistError,
    build_credentials_service,
    is_keyring_usable,
)
from sqlit.domains.connections.domain.config import (
    AUTH_TYPE_LABELS,
    AuthType,
    ConnectionConfig,
    DatabaseType,
    get_database_type_labels,
)
from sqlit.domains.connections.providers.catalog import get_provider_schema
from sqlit.shared.app.runtime import RuntimeConfig
from sqlit.shared.app.services import AppServices, build_app_services

from .helpers import build_connection_config_from_args


def _find_connection_index(connections: list[ConnectionConfig], name: str) -> int | None:
    for idx, conn in enumerate(connections):
        if conn.name == name:
            return idx
    return None


def _ensure_password_storage(
    services: AppServices,
    config: ConnectionConfig,
) -> None:
    has_db_password = bool(config.tcp_endpoint and config.tcp_endpoint.password)
    has_ssh_password = bool(config.tunnel and config.tunnel.password)
    if (has_db_password or has_ssh_password) and not is_keyring_usable():
        if not _maybe_prompt_plaintext_credentials(services):
            _clear_passwords_if_not_persisted(config)


def _maybe_prompt_plaintext_credentials(services: AppServices) -> bool:
    """Ensure plaintext credential storage preference is set when keyring isn't usable.

    Returns True if plaintext storage is allowed; False otherwise.
    """
    if is_keyring_usable():
        return False

    settings = services.settings_store.load_all()
    existing = settings.get(ALLOW_PLAINTEXT_CREDENTIALS_SETTING)
    if isinstance(existing, bool):
        if existing:
            services.credentials_service = build_credentials_service(services.settings_store)
            if hasattr(services.connection_store, "set_credentials_service"):
                services.connection_store.set_credentials_service(services.credentials_service)
        return existing

    if not sys.stdin.isatty():
        return False

    answer = input("Keyring isn't available. Save passwords as plaintext in ~/.sqlit/? [y/N]: ").strip().lower()
    allow = answer in {"y", "yes"}
    settings[ALLOW_PLAINTEXT_CREDENTIALS_SETTING] = allow
    services.settings_store.save_all(settings)
    if allow:
        services.credentials_service = build_credentials_service(services.settings_store)
        if hasattr(services.connection_store, "set_credentials_service"):
            services.connection_store.set_credentials_service(services.credentials_service)
    return allow


def _clear_passwords_if_not_persisted(config: ConnectionConfig) -> None:
    endpoint = config.tcp_endpoint
    if endpoint:
        endpoint.password = ""
    if config.tunnel:
        config.tunnel.password = ""


def _save_connections(services: AppServices, connections: list[ConnectionConfig]) -> None:
    try:
        services.connection_store.save_all(connections)
    except CredentialsPersistError as exc:
        print(f"Warning: {exc}", file=sys.stderr)


def cmd_connection_list(args: Any, *, services: AppServices | None = None) -> int:
    """List all saved connections."""
    services = services or build_app_services(RuntimeConfig.from_env())
    connections = services.connection_store.load_all()
    if not connections:
        print("No saved connections.")
        return 0

    print(f"{'Name':<20} {'Type':<10} {'Connection Info':<40} {'Auth Type':<25}")
    print("-" * 95)
    labels = get_database_type_labels()
    for conn in connections:
        db_type_label = labels.get(conn.get_db_type(), conn.db_type)
        provider = services.provider_factory(conn.db_type)
        if provider.metadata.is_file_based:
            file_endpoint = conn.file_endpoint
            file_path = str(file_endpoint.path if file_endpoint else "")
            conn_info = file_path[:38] + ".." if len(file_path) > 40 else file_path
            auth_label = "N/A"
        elif provider.metadata.has_advanced_auth:
            endpoint = conn.tcp_endpoint
            host = endpoint.host if endpoint else ""
            database = endpoint.database if endpoint else ""
            conn_info = f"{host}@{database}" if database else host
            conn_info = conn_info[:38] + ".." if len(conn_info) > 40 else conn_info
            auth_value = str(conn.get_option("auth_type", ""))
            auth_type = provider.get_auth_type(conn)
            auth_label = AUTH_TYPE_LABELS.get(auth_type, auth_value) if auth_type else auth_value
        else:
            # Server-based databases with simple auth
            endpoint = conn.tcp_endpoint
            host = endpoint.host if endpoint else ""
            database = endpoint.database if endpoint else ""
            conn_info = f"{host}@{database}" if database else host
            conn_info = conn_info[:38] + ".." if len(conn_info) > 40 else conn_info
            auth_label = f"User: {endpoint.username}" if endpoint and endpoint.username else "N/A"
        print(f"{conn.name:<20} {db_type_label:<10} {conn_info:<40} {auth_label:<25}")
    return 0


def cmd_connection_create(args: Any, *, services: AppServices | None = None) -> int:
    """Create a new connection."""
    from sqlit.domains.connections.app.url_parser import is_connection_url, parse_connection_url

    services = services or build_app_services(RuntimeConfig.from_env())
    connections = services.connection_store.load_all()

    # Handle URL-based connection creation
    url = getattr(args, "url", None)
    if url:
        if not is_connection_url(url):
            print(f"Error: Invalid connection URL: {url}")
            return 1

        url_name = getattr(args, "url_name", None)
        if not url_name:
            print("Error: --name is required when using --url")
            return 1

        if any(c.name == url_name for c in connections):
            print(f"Error: Connection '{url_name}' already exists. Use 'edit' to modify it.")
            return 1

        try:
            config = parse_connection_url(url, name=url_name)
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1

        connections.append(config)
        has_db_password = bool(config.tcp_endpoint and config.tcp_endpoint.password)
        has_ssh_password = bool(config.tunnel and config.tunnel.password)
        if (has_db_password or has_ssh_password) and not is_keyring_usable():
            if not _maybe_prompt_plaintext_credentials(services):
                _clear_passwords_if_not_persisted(config)
        _save_connections(services, connections)
        print(f"Connection '{url_name}' created successfully.")
        return 0

    # Handle provider-based connection creation (existing behavior)
    if not getattr(args, "provider", None):
        print("Error: provider or --url is required.")
        print("Examples:")
        print("  sqlit connections add postgresql --name MyDB --server localhost ...")
        print("  sqlit connections add --url postgresql://user:pass@host/db --name MyDB")
        return 1

    if any(c.name == args.name for c in connections):
        print(f"Error: Connection '{args.name}' already exists. Use 'edit' to modify it.")
        return 1

    db_type = getattr(args, "provider", None)
    if not isinstance(db_type, str):
        print("Error: provider is required.")
        return 1
    try:
        DatabaseType(db_type)
    except ValueError:
        valid_types = ", ".join(t.value for t in DatabaseType)
        print(f"Error: Invalid database type '{db_type}'. Valid types: {valid_types}")
        return 1

    schema = get_provider_schema(db_type)
    try:
        config = build_connection_config_from_args(
            schema,
            args,
            name=args.name,
            default_name=None,
            strict=True,
        )
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    connections.append(config)
    _ensure_password_storage(services, config)
    _save_connections(services, connections)
    print(f"Connection '{args.name}' created successfully.")
    return 0


def cmd_connection_edit(args: Any, *, services: AppServices | None = None) -> int:
    """Edit an existing connection."""
    services = services or build_app_services(RuntimeConfig.from_env())
    connections = services.connection_store.load_all()

    conn_idx = _find_connection_index(connections, args.connection_name)
    if conn_idx is None:
        print(f"Error: Connection '{args.connection_name}' not found.")
        return 1

    conn = connections[conn_idx]

    if args.name:
        if args.name != conn.name and any(c.name == args.name for c in connections):
            print(f"Error: Connection '{args.name}' already exists.")
            return 1
        conn.name = args.name

    endpoint = conn.tcp_endpoint
    server = getattr(args, "server", None) or getattr(args, "host", None)
    if endpoint:
        if server:
            endpoint.host = server
        if args.port:
            endpoint.port = args.port
        if args.database:
            endpoint.database = args.database
    if args.auth_type:
        try:
            auth_type = AuthType(args.auth_type)
            conn.set_option("auth_type", auth_type.value)
            conn.set_option("trusted_connection", auth_type == AuthType.WINDOWS)
        except ValueError:
            valid_types = ", ".join(t.value for t in AuthType)
            print(f"Error: Invalid auth type '{args.auth_type}'. Valid types: {valid_types}")
            return 1
    if endpoint:
        if args.username is not None:
            endpoint.username = args.username
        if args.password is not None:
            endpoint.password = args.password

    file_path = getattr(args, "file_path", None)
    if file_path is not None:
        if conn.file_endpoint:
            conn.file_endpoint.path = file_path
        else:
            from sqlit.domains.connections.domain.config import FileEndpoint

            conn.endpoint = FileEndpoint(path=file_path)

    _ensure_password_storage(services, conn)

    _save_connections(services, connections)
    print(f"Connection '{conn.name}' updated successfully.")
    return 0


def cmd_connection_delete(args: Any, *, services: AppServices | None = None) -> int:
    """Delete a connection."""
    services = services or build_app_services(RuntimeConfig.from_env())
    connections = services.connection_store.load_all()

    conn_idx = _find_connection_index(connections, args.connection_name)
    if conn_idx is None:
        print(f"Error: Connection '{args.connection_name}' not found.")
        return 1

    deleted = connections.pop(conn_idx)
    _save_connections(services, connections)
    print(f"Connection '{deleted.name}' deleted successfully.")
    return 0


def cmd_docker_list(args: Any, *, services: AppServices | None = None) -> int:
    """List detected Docker database containers."""
    from sqlit.domains.connections.discovery.docker_detector import (
        ContainerStatus,
        DockerStatus,
    )

    services = services or build_app_services(RuntimeConfig.from_env())
    status, containers = services.docker_detector()

    if status == DockerStatus.NOT_INSTALLED:
        print("Error: Docker Python library not installed.")
        print("Install it with: pip install docker")
        return 1
    elif status == DockerStatus.NOT_RUNNING:
        print("Error: Docker is not running.")
        return 1
    elif status == DockerStatus.NOT_ACCESSIBLE:
        print("Error: Docker is not accessible (permission denied).")
        print("Try adding your user to the docker group or running with sudo.")
        return 1

    if not containers:
        print("No database containers found.")
        return 0

    running = [c for c in containers if c.status == ContainerStatus.RUNNING]
    exited = [c for c in containers if c.status == ContainerStatus.EXITED]

    print(f"{'Container':<25} {'Type':<12} {'Port':<8} {'Database':<15} {'Status':<10}")
    print("-" * 75)

    for c in running:
        port_str = str(c.port) if c.port else "-"
        db_str = c.database[:13] + ".." if c.database and len(c.database) > 15 else (c.database or "-")
        name_str = c.container_name[:23] + ".." if len(c.container_name) > 25 else c.container_name
        print(f"{name_str:<25} {c.db_type:<12} {port_str:<8} {db_str:<15} {'running':<10}")

    for c in exited:
        port_str = "-"
        db_str = c.database[:13] + ".." if c.database and len(c.database) > 15 else (c.database or "-")
        name_str = c.container_name[:23] + ".." if len(c.container_name) > 25 else c.container_name
        print(f"{name_str:<25} {c.db_type:<12} {port_str:<8} {db_str:<15} {'exited':<10}")

    print(f"\nFound {len(running)} running, {len(exited)} exited database container(s).")
    return 0
