"""Label and node helpers for explorer tree mixins."""

from __future__ import annotations

from typing import Any

from rich.markup import escape as escape_markup

from sqlit.domains.connections.providers.metadata import get_badge_label, get_connection_display_info
from sqlit.shared.ui.protocols import TreeMixinHost
from sqlit.shared.ui.spinner import SPINNER_FRAMES


def _dim_color(hex_color: str, factor: float = 0.3) -> str:
    """Dim a hex color by reducing its brightness."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return f"#{hex_color}"
    r = int(int(hex_color[0:2], 16) * factor)
    g = int(int(hex_color[2:4], 16) * factor)
    b = int(int(hex_color[4:6], 16) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


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
        selected = getattr(self, "_selected_connection_names", set())
        is_selected = getattr(conn, "name", None) in selected
        if status == "connected":
            primary = getattr(getattr(self, "current_theme", None), "primary", "#7E9CD8")
            label = (
                f"[{primary}]* {source_emoji}{escaped_name}[/]"
                f" [{db_type_label}] ({display_info})"
            )
        elif status == "connecting":
            frame = spinner or SPINNER_FRAMES[0]
            label = (
                f"[#FBBF24]{frame}[/] {source_emoji}{escaped_name}"
                " [dim italic]Connecting...[/]"
            )
        else:
            label = (
                f"[dim]{source_emoji}{escaped_name}"
                f" [{db_type_label}] ({display_info})[/]"
            )

        if is_selected:
            primary = getattr(getattr(self, "current_theme", None), "primary", "#7E9CD8")
            dimmed = _dim_color(primary, 0.5)
            return f"[on {dimmed}]{label}[/]"
        return label

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
