"""JSON tree viewer widget for sqlit."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from typing import Any

from rich.highlighter import ReprHighlighter
from rich.text import Text
from textual.widgets import Tree
from textual.widgets.tree import TreeNode


def parse_json_value(value: str) -> tuple[bool, dict | list | None]:
    """Parse a string as JSON and return (is_json, parsed_value).

    Tries standard JSON parsing first, then falls back to Python literal_eval
    for Python-style dicts/lists.
    """
    stripped = value.strip()
    if not stripped or stripped[0] not in "{[":
        return False, None

    try:
        parsed = json.loads(stripped)
        return True, parsed
    except (json.JSONDecodeError, ValueError):
        pass

    try:
        parsed = ast.literal_eval(stripped)
        if isinstance(parsed, dict | list):
            return True, parsed
    except (ValueError, SyntaxError):
        pass

    return False, None


@dataclass
class JSONNodeData:
    """Data stored in each tree node."""

    key: str | None  # The key/index for this node (None for root)
    value: Any  # The actual value at this node


class JSONTreeView(Tree[JSONNodeData]):
    """Interactive JSON tree viewer with expand/collapse support."""

    DEFAULT_CSS = """
    JSONTreeView {
        height: 1fr;
        background: $surface;
    }

    JSONTreeView > .tree--guides {
        color: $text-muted;
    }

    JSONTreeView > .tree--cursor {
        background: $accent;
        color: $text;
    }

    JSONTreeView.flash-cursor > .tree--cursor {
        background: $success 30%;
    }

    JSONTreeView.flash-all {
        background: $success 20%;
    }
    """

    def __init__(
        self,
        label: str = "JSON",
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(label, id=id, classes=classes)
        self._raw_json: str = ""
        self._highlighter = ReprHighlighter()

    def set_json(self, data: str | dict | list, label: str = "JSON") -> None:
        """Set JSON data to display in the tree."""
        self._raw_json = data if isinstance(data, str) else json.dumps(data)

        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, ValueError):
                self.root.set_label(Text("Invalid JSON", style="red"))
                return

        self.clear()
        self.root.set_label(Text(f"{{}} {label}" if isinstance(data, dict) else f"[] {label}"))
        self.root.data = JSONNodeData(key=None, value=data)
        self._add_json_node(self.root, data)
        self.root.expand()

    def _add_json_node(self, node: TreeNode[JSONNodeData], data: Any, key: str | None = None) -> None:
        """Recursively add JSON data to tree nodes."""
        if isinstance(data, dict):
            if key is not None:
                label = Text.assemble(Text("{} ", style="bold cyan"), Text(key))
                child = node.add(label, data=JSONNodeData(key=key, value=data))
            else:
                child = node
            for k, v in data.items():
                self._add_json_node(child, v, k)
        elif isinstance(data, list):
            if key is not None:
                label = Text.assemble(
                    Text("[] ", style="bold magenta"),
                    Text(key),
                    Text(f" ({len(data)})", style="dim"),
                )
                child = node.add(label, data=JSONNodeData(key=key, value=data))
            else:
                child = node
            for i, v in enumerate(data):
                self._add_json_node(child, v, f"[{i}]")
        else:
            if key is not None:
                value_text = self._format_value(data)
                label = Text.assemble(
                    Text(f"{key}", style="bold"),
                    Text(": ", style="dim"),
                    value_text,
                )
                leaf = node.add_leaf(label, data=JSONNodeData(key=key, value=data))
                leaf.allow_expand = False
            else:
                node.add_leaf(self._format_value(data), data=JSONNodeData(key=None, value=data))

    def _format_value(self, value: Any) -> Text:
        """Format a leaf value with syntax highlighting."""
        if value is None:
            return Text("null", style="italic dim")
        elif isinstance(value, bool):
            return Text(str(value).lower(), style="italic cyan")
        elif isinstance(value, int | float):
            return Text(str(value), style="bold blue")
        elif isinstance(value, str):
            if len(value) > 100:
                display = f'"{value[:100]}..."'
            else:
                display = f'"{value}"'
            return Text(display, style="green")
        else:
            return self._highlighter(repr(value))

    def action_expand_all(self) -> None:
        """Expand all nodes in the tree."""

        def expand_recursive(node: TreeNode[JSONNodeData]) -> None:
            node.expand()
            for child in node.children:
                expand_recursive(child)

        expand_recursive(self.root)

    def action_collapse_all(self) -> None:
        """Collapse all nodes except root."""

        def collapse_recursive(node: TreeNode[JSONNodeData]) -> None:
            for child in node.children:
                collapse_recursive(child)
                child.collapse()

        collapse_recursive(self.root)
        self.root.expand()

    @property
    def raw_json(self) -> str:
        """Get the raw JSON string for copying."""
        return self._raw_json

    def get_cursor_key(self) -> str | None:
        """Get the key of the currently selected node."""
        node = self.cursor_node
        if node is None or node.data is None:
            return None
        return node.data.key

    def get_cursor_value(self) -> Any:
        """Get the value of the currently selected node."""
        node = self.cursor_node
        if node is None or node.data is None:
            return None
        return node.data.value

    def get_cursor_value_json(self) -> str:
        """Get the value of the currently selected node as JSON string."""
        value = self.get_cursor_value()
        if value is None:
            return "null"
        return json.dumps(value, indent=2, ensure_ascii=False)

    def get_cursor_field_json(self) -> str | None:
        """Get the current field as 'key': value JSON string."""
        node = self.cursor_node
        if node is None or node.data is None:
            return None
        key = node.data.key
        value = node.data.value
        if key is None:
            # Root node - just return the value
            return json.dumps(value, indent=2, ensure_ascii=False)
        # Check if key is an array index like [0]
        if key.startswith("[") and key.endswith("]"):
            # Array element - just return the value
            return json.dumps(value, indent=2, ensure_ascii=False)
        # Object field - return as "key": value
        return f'"{key}": {json.dumps(value, ensure_ascii=False)}'
