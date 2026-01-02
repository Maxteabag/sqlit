"""Docker tab helpers for the connection picker."""

from __future__ import annotations

from textual.widgets.option_list import Option

from sqlit.domains.connections.discovery.docker_detector import DetectedContainer
from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.providers.metadata import get_connection_display_info
from sqlit.shared.core.utils import fuzzy_match, highlight_matches

DOCKER_PREFIX = "docker:"


def is_docker_option_id(option_id: str) -> bool:
    return option_id.startswith(DOCKER_PREFIX)


def find_container_by_id(
    containers: list[DetectedContainer],
    container_id: str,
) -> DetectedContainer | None:
    for container in containers:
        if container.container_id == container_id:
            return container
    return None


def is_container_saved(
    connections: list[ConnectionConfig],
    container: DetectedContainer,
) -> bool:
    for conn in connections:
        if conn.name == container.container_name:
            return True

        # Only match on technical details if this is a docker-sourced connection
        if conn.source != "docker":
            continue

        endpoint = conn.tcp_endpoint
        if (
            endpoint
            and conn.db_type == container.db_type
            and endpoint.host in ("localhost", "127.0.0.1", container.host)
            and endpoint.port == str(container.port)
        ):
            if container.database:
                if endpoint.database == container.database:
                    return True
            else:
                return True
    return False


def find_matching_saved_connection(
    connections: list[ConnectionConfig],
    container: DetectedContainer,
) -> ConnectionConfig | None:
    for conn in connections:
        if conn.name == container.container_name:
            return conn

        # Only match on technical details if this is a docker-sourced connection
        if conn.source != "docker":
            continue

        endpoint = conn.tcp_endpoint
        if (
            endpoint
            and conn.db_type == container.db_type
            and endpoint.host in ("localhost", "127.0.0.1", container.host)
            and endpoint.port == str(container.port)
        ):
            if container.database:
                if endpoint.database == container.database:
                    return conn
            else:
                return conn
    return None


def build_docker_options(
    connections: list[ConnectionConfig],
    containers: list[DetectedContainer],
    pattern: str,
    *,
    loading: bool,
    status_message: str | None,
) -> list[Option]:
    options: list[Option] = []

    saved_options: list[Option] = []
    for conn in connections:
        if conn.source != "docker":
            continue
        matches, indices = fuzzy_match(pattern, conn.name)
        if matches or not pattern:
            display = highlight_matches(conn.name, indices)
            db_type = conn.db_type.upper() if conn.db_type else "DB"
            info = get_connection_display_info(conn)
            saved_options.append(
                Option(f"docker {display} [{db_type}] [dim]({info})[/]", id=conn.name)
            )

    running_options: list[Option] = []
    exited_options: list[Option] = []
    for container in containers:
        if is_container_saved(connections, container):
            continue

        matches, indices = fuzzy_match(pattern, container.container_name)
        if matches or not pattern:
            display = highlight_matches(container.container_name, indices)
            db_label = container.get_display_name().split("(")[-1].rstrip(")")
            port_info = f":{container.port}" if container.port else ""

            if container.is_running:
                if container.connectable:
                    running_options.append(
                        Option(
                            f"docker {display} [{db_label}] [dim](localhost{port_info})[/]",
                            id=f"{DOCKER_PREFIX}{container.container_id}",
                        )
                    )
                else:
                    running_options.append(
                        Option(
                            f"docker {display} [{db_label}] [dim](not exposed)[/]",
                            id=f"{DOCKER_PREFIX}{container.container_id}",
                            disabled=True,
                        )
                    )
            else:
                exited_options.append(
                    Option(
                        f"[dim]docker {display} [{db_label}] (Stopped)[/]",
                        id=f"{DOCKER_PREFIX}{container.container_id}",
                    )
                )

    options.append(Option("[bold]Saved[/]", id="_header_docker_saved", disabled=True))

    if saved_options:
        options.extend(saved_options)
    else:
        options.append(Option("[dim](no saved Docker connections)[/]", id="_empty_docker_saved", disabled=True))

    options.append(Option("", id="_spacer1", disabled=True))
    options.append(Option("[bold]Running[/]", id="_header_docker", disabled=True))

    if loading:
        options.append(Option("[dim italic]Loading...[/]", id="_docker_loading", disabled=True))
    elif running_options:
        options.extend(running_options)
    elif status_message:
        options.append(Option(f"[dim]{status_message}[/]", id="_docker_status", disabled=True))
    else:
        options.append(Option("[dim](no running containers)[/]", id="_docker_empty", disabled=True))

    if exited_options:
        options.append(Option("", id="_spacer2", disabled=True))
        options.append(Option("[bold]Stopped[/]", id="_header_docker_unavailable", disabled=True))
        options.extend(exited_options)

    return options
