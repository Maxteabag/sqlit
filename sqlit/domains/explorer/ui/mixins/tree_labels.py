"""Label and node helpers for explorer tree mixins."""

from __future__ import annotations

from typing import Any

from rich.markup import escape as escape_markup

from sqlit.domains.connections.providers.metadata import get_badge_label, get_connection_display_info
from sqlit.shared.ui.protocols import TreeMixinHost
from sqlit.shared.ui.spinner import SPINNER_FRAMES


class TreeLabelMixin:
    """Mixin providing connection label helpers."""

    def _db_type_badge(self, db_type: str) -> str:
        """Get short badge for database type."""
        return get_badge_label(db_type)

    def _format_connection_label(self, conn: Any, status: str, spinner: str | None = None) -> str:
        display_info = escape_markup(get_connection_display_info(conn))
        db_type_label = self._db_type_badge(conn.db_type)
        escaped_name = escape_markup(conn.name)
        source_emoji = conn.get_source_emoji()

        if status == "connected":
            return f"[#4ADE80]* {source_emoji}{escaped_name}[/] [{db_type_label}] ({display_info})"
        if status == "connecting":
            frame = spinner or SPINNER_FRAMES[0]
            return (
                f"[#FBBF24]{frame}[/] {source_emoji}{escaped_name} [dim italic]Connecting...[/]"
            )
        return f"{source_emoji}[dim]{escaped_name}[/dim] [{db_type_label}] ({display_info})"

    def _connect_spinner_frame(self: TreeMixinHost) -> str:
        spinner = getattr(self, "_connect_spinner", None)
        return spinner.frame if spinner else SPINNER_FRAMES[0]

    def _get_node_kind(self, node: Any) -> str:
        data = getattr(node, "data", None)
        if data is None:
            return ""
        getter = getattr(data, "get_node_kind", None)
        if callable(getter):
            return str(getter())
        return ""

    def _get_node_path_part(self, data: Any) -> str:
        getter = getattr(data, "get_node_path_part", None)
        if callable(getter):
            return str(getter())
        return ""
