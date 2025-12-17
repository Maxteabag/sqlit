"""Tree filter mixin for SSMSTUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.markup import escape as escape_markup

from ...utils import fuzzy_match, highlight_matches
from ..protocols import AppProtocol
from ..tree_nodes import (
    ColumnNode,
    ConnectionNode,
    DatabaseNode,
    FolderNode,
    ProcedureNode,
    SchemaNode,
    TableNode,
    ViewNode,
)

if TYPE_CHECKING:
    pass


class TreeFilterMixin:
    """Mixin providing tree filter functionality."""

    _tree_filter_visible: bool = False
    _tree_filter_text: str = ""
    _tree_filter_matches: list[Any] = []
    _tree_filter_match_index: int = 0
    _tree_original_labels: dict[int, str] = {}

    def action_tree_filter(self: AppProtocol) -> None:
        """Open the tree filter."""
        if not self.object_tree.has_focus:
            self.object_tree.focus()

        self._tree_filter_visible = True
        self._tree_filter_text = ""
        self._tree_filter_matches = []
        self._tree_filter_match_index = 0
        self._tree_original_labels = {}

        self.tree_filter_input.show()
        self._update_tree_filter()
        self._update_footer_bindings()

    def action_tree_filter_close(self: AppProtocol) -> None:
        """Close the tree filter and restore tree."""
        self._tree_filter_visible = False
        self._tree_filter_text = ""
        self.tree_filter_input.hide()
        self._restore_tree_labels()
        self._show_all_tree_nodes()
        self._update_footer_bindings()

    def action_tree_filter_accept(self: AppProtocol) -> None:
        """Accept current filter selection and close."""
        self.action_tree_filter_close()

    def action_tree_filter_next(self: AppProtocol) -> None:
        """Move to next filter match."""
        if not self._tree_filter_matches:
            return
        self._tree_filter_match_index = (self._tree_filter_match_index + 1) % len(
            self._tree_filter_matches
        )
        self._jump_to_current_match()

    def action_tree_filter_prev(self: AppProtocol) -> None:
        """Move to previous filter match."""
        if not self._tree_filter_matches:
            return
        self._tree_filter_match_index = (self._tree_filter_match_index - 1) % len(
            self._tree_filter_matches
        )
        self._jump_to_current_match()

    def _jump_to_current_match(self: AppProtocol) -> None:
        """Jump to the current match in the tree."""
        if not self._tree_filter_matches:
            return
        node = self._tree_filter_matches[self._tree_filter_match_index]
        # Expand ancestors to make node visible
        self._expand_ancestors(node)
        # Select the node
        self.object_tree.select_node(node)

    def _expand_ancestors(self: AppProtocol, node: Any) -> None:
        """Expand all ancestor nodes to make a node visible."""
        ancestors = []
        current = node.parent
        while current and current != self.object_tree.root:
            ancestors.append(current)
            current = current.parent
        # Expand from root down
        for ancestor in reversed(ancestors):
            ancestor.expand()

    def on_key(self: AppProtocol, event: Any) -> None:
        """Handle key events when tree filter is active."""
        if not self._tree_filter_visible:
            # Pass to next mixin in chain (e.g., AutocompleteMixin)
            super().on_key(event)  # type: ignore[misc]
            return

        key = event.key

        # Handle backspace
        if key == "backspace":
            if self._tree_filter_text:
                self._tree_filter_text = self._tree_filter_text[:-1]
                self._update_tree_filter()
            else:
                # Exit filter when backspacing with no text
                self.action_tree_filter_close()
            event.prevent_default()
            event.stop()
            return

        # Handle printable characters
        if len(key) == 1 and key.isprintable():
            self._tree_filter_text += key
            self._update_tree_filter()
            event.prevent_default()
            event.stop()
            return

        # Pass unhandled keys to next mixin
        super().on_key(event)  # type: ignore[misc]

    def _update_tree_filter(self: AppProtocol) -> None:
        """Update the tree based on current filter text."""
        self._restore_tree_labels()
        total = self._count_all_nodes()

        if not self._tree_filter_text:
            self._show_all_tree_nodes()
            self._tree_filter_matches = []
            self.tree_filter_input.set_filter("", 0, total)
            return

        # Find all matching nodes
        matches: list[Any] = []
        self._find_matching_nodes(self.object_tree.root, matches)

        self._tree_filter_matches = matches
        self._tree_filter_match_index = 0

        # Hide non-matching nodes and highlight matches
        self._apply_filter_to_tree()

        # Update filter display
        self.tree_filter_input.set_filter(
            self._tree_filter_text, len(matches), total
        )

        # Jump to first match
        if matches:
            self._jump_to_current_match()

    def _find_matching_nodes(
        self: AppProtocol, node: Any, matches: list
    ) -> bool:
        """Recursively find nodes matching the filter.

        Returns True if this node or any descendant matches.
        """
        node_matches = False
        has_matching_child = False

        # Check children first
        for child in node.children:
            if self._find_matching_nodes(child, matches):
                has_matching_child = True

        # Get node label text for matching
        label_text = self._get_node_label_text(node)
        if label_text:
            matched, indices = fuzzy_match(self._tree_filter_text, label_text)
            if matched:
                node_matches = True
                matches.append(node)
                # Store original label and apply highlighting
                self._tree_original_labels[id(node)] = str(node.label)
                highlighted = highlight_matches(
                    escape_markup(label_text), indices, style="bold #FFFF00"
                )
                # Preserve any existing markup prefix (like icons, colors)
                node.set_label(self._rebuild_label_with_highlight(node, highlighted))

        return node_matches or has_matching_child

    def _get_node_label_text(self, node: Any) -> str:
        """Get the plain text label for a node."""
        data = node.data
        if data is None:
            return ""

        if isinstance(data, ConnectionNode):
            return data.config.name
        elif isinstance(data, DatabaseNode):
            return data.name
        elif isinstance(data, FolderNode):
            return data.folder_type
        elif isinstance(data, SchemaNode):
            return data.schema
        elif isinstance(data, TableNode):
            return data.name
        elif isinstance(data, ViewNode):
            return data.name
        elif isinstance(data, ProcedureNode):
            return data.name
        elif isinstance(data, ColumnNode):
            return data.name
        return ""

    def _rebuild_label_with_highlight(self, node: Any, highlighted_text: str) -> str:
        """Rebuild the node label with highlighted text."""
        data = node.data
        if data is None:
            return highlighted_text

        # For simple nodes, just return highlighted text
        if isinstance(data, TableNode | ViewNode | ProcedureNode):
            return highlighted_text
        elif isinstance(data, ColumnNode):
            # Columns show "name type" format - only highlight name
            return highlighted_text
        elif isinstance(data, ConnectionNode):
            # Connections have format "[color]* name[/] [TYPE] (info)"
            # Just replace the name portion
            return highlighted_text
        elif isinstance(data, DatabaseNode | SchemaNode | FolderNode):
            return highlighted_text

        return highlighted_text

    def _apply_filter_to_tree(self: AppProtocol) -> None:
        """Hide nodes that don't match and aren't ancestors of matches."""
        match_ids = {id(n) for n in self._tree_filter_matches}
        ancestor_ids = set()

        # Collect all ancestor IDs
        for node in self._tree_filter_matches:
            current = node.parent
            while current and current != self.object_tree.root:
                ancestor_ids.add(id(current))
                current = current.parent

        # Hide non-matching, non-ancestor nodes
        self._set_node_visibility(
            self.object_tree.root, match_ids, ancestor_ids, visible=True
        )

    def _set_node_visibility(
        self: AppProtocol,
        node: Any,
        match_ids: set,
        ancestor_ids: set,
        visible: bool,
    ) -> None:
        """Recursively set node visibility."""
        for child in node.children:
            child_id = id(child)
            is_match = child_id in match_ids
            is_ancestor = child_id in ancestor_ids
            should_show = is_match or is_ancestor or not self._tree_filter_text

            # Use display style to hide/show
            # Note: Textual Tree doesn't have per-node visibility,
            # so we'll dim non-matching nodes instead
            if not should_show and self._tree_filter_text:
                # Dim non-matching nodes
                original = self._tree_original_labels.get(child_id, str(child.label))
                if child_id not in self._tree_original_labels:
                    self._tree_original_labels[child_id] = original
                child.set_label(f"[dim]{escape_markup(self._get_node_label_text(child))}[/]")

            self._set_node_visibility(child, match_ids, ancestor_ids, should_show)

    def _show_all_tree_nodes(self: AppProtocol) -> None:
        """Show all tree nodes (remove filter dimming)."""
        # Labels are restored by _restore_tree_labels
        pass

    def _restore_tree_labels(self: AppProtocol) -> None:
        """Restore original labels for all modified nodes."""
        def restore_node(node: Any) -> None:
            node_id = id(node)
            if node_id in self._tree_original_labels:
                node.set_label(self._tree_original_labels[node_id])
            for child in node.children:
                restore_node(child)

        restore_node(self.object_tree.root)
        self._tree_original_labels = {}

    def _count_all_nodes(self: AppProtocol) -> int:
        """Count all searchable nodes in the tree."""
        count = 0

        def count_nodes(node: Any) -> None:
            nonlocal count
            if node.data and self._get_node_label_text(node):
                count += 1
            for child in node.children:
                count_nodes(child)

        count_nodes(self.object_tree.root)
        return count
