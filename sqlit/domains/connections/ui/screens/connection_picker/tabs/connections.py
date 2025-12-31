"""Connections tab helpers for the connection picker."""

from __future__ import annotations

from textual.widgets.option_list import Option

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.providers.metadata import get_connection_display_info
from sqlit.shared.core.utils import fuzzy_match, highlight_matches


def build_connections_options(
    connections: list[ConnectionConfig],
    pattern: str,
) -> list[Option]:
    options: list[Option] = []

    saved_options: list[Option] = []
    for conn in connections:
        matches, indices = fuzzy_match(pattern, conn.name)
        if matches or not pattern:
            display = highlight_matches(conn.name, indices)
            db_type = conn.db_type.upper() if conn.db_type else "DB"
            info = get_connection_display_info(conn)
            source_prefix = ""
            if conn.source == "docker":
                source_prefix = "docker "
            saved_options.append(
                Option(f"{source_prefix}{display} [{db_type}] [dim]({info})[/]", id=conn.name)
            )

    options.append(Option("[bold]Saved[/]", id="_header_saved", disabled=True))

    if saved_options:
        options.extend(saved_options)
    else:
        options.append(Option("[dim](no saved connections)[/]", id="_empty_saved", disabled=True))

    return options


def find_connection_by_name(
    connections: list[ConnectionConfig],
    name: str,
) -> ConnectionConfig | None:
    for conn in connections:
        if conn.name == name:
            return conn
    return None
