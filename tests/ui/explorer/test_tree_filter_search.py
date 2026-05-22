"""Tests for the explorer tree '/' search filter.

Simulates typing into the tree filter and pressing backspace to verify that
narrowing then widening the query restores previously-matching nodes.

Scenario:
1. Tree has many connection nodes; some contain 't' in their name.
2. Open filter and type 't' -> only 't'-matching nodes are visible.
3. Type 't' again (filter is 'tt'), which matches none -> tree becomes empty.
4. Press backspace (filter back to 't') -> 't'-matching nodes reappear.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from sqlit.domains.explorer.domain.tree_nodes import ConnectionNode
from sqlit.domains.explorer.ui.mixins.tree_filter import TreeFilterMixin


class MockTreeNode:
    """Mock Textual tree node supporting add/remove/expand/set_label."""

    def __init__(self, label: str = "", data=None, parent: "MockTreeNode | None" = None):
        self.label = label
        self.data = data
        self.parent = parent
        self.children: list[MockTreeNode] = []
        self.allow_expand = False
        self.is_expanded = False

    def add(self, label: str, data=None) -> "MockTreeNode":
        child = MockTreeNode(label, data=data, parent=self)
        self.children.append(child)
        return child

    def remove(self) -> None:
        if self.parent and self in self.parent.children:
            self.parent.children.remove(self)

    def expand(self) -> None:
        self.is_expanded = True

    def collapse(self) -> None:
        self.is_expanded = False

    def set_label(self, label: str) -> None:
        self.label = label


class MockTree:
    """Mock Tree widget exposing the root node and basic ops."""

    def __init__(self):
        self.root = MockTreeNode("root")
        self.has_focus = True
        self.selected_node: MockTreeNode | None = None

    def select_node(self, node: MockTreeNode) -> None:
        self.selected_node = node

    def focus(self) -> None:
        self.has_focus = True


class MockFilterInput:
    """Mock TreeFilterInput capturing the last set_filter call."""

    def __init__(self):
        self.visible = False
        self.last_text = ""
        self.last_match_count = 0
        self.last_total_count = 0

    def show(self) -> None:
        self.visible = True

    def hide(self) -> None:
        self.visible = False

    def set_filter(self, text: str, match_count: int = 0, total_count: int = 0) -> None:
        self.last_text = text
        self.last_match_count = match_count
        self.last_total_count = total_count


def _make_connection_node(name: str) -> ConnectionNode:
    """Create a ConnectionNode by constructing a minimal ConnectionConfig."""
    config = MagicMock()
    config.name = name
    node = object.__new__(ConnectionNode)
    object.__setattr__(node, "config", config)
    return node


class _FilterHost(TreeFilterMixin):
    """Concrete host that uses TreeFilterMixin and rebuilds the tree on refresh.

    `refresh_tree` here mirrors the real behavior: it discards the current
    tree contents and rebuilds them from the stored original connection list.
    """

    def __init__(self, connection_names: list[str]):
        self._connection_names = connection_names
        self.object_tree = MockTree()
        self.tree_filter_input = MockFilterInput()
        self._populate()

    def _populate(self) -> None:
        self.object_tree.root.children = []
        for name in self._connection_names:
            data = _make_connection_node(name)
            child = self.object_tree.root.add(name, data=data)
            child.allow_expand = True

    # Required by TreeFilterMixin when query becomes empty.
    def refresh_tree(self) -> None:
        self._populate()

    # No-op stubs required by the mixin.
    def _update_footer_bindings(self) -> None:
        pass

    def _activate_tree_node(self, _node) -> None:
        pass


def _visible_node_names(host: _FilterHost) -> list[str]:
    names: list[str] = []
    for child in host.object_tree.root.children:
        data = child.data
        if data is not None and hasattr(data, "get_label_text"):
            names.append(data.get_label_text())
    return names


class TestTreeFilterSearch:
    """End-to-end-ish tests of the search behavior with typing and backspace."""

    CONNECTION_NAMES = [
        "alpha",
        "bravo",
        "gamma",
        "test-server",
        "atlas",
        "tipi",
        "production",
        "staging",
        "delta",
        "omega",
    ]
    # Names that contain a 't' (case-insensitive)
    T_MATCHES = {
        "test-server",
        "atlas",
        "tipi",
        "production",
        "staging",
        "delta",
    }

    def _open_filter(self, host: _FilterHost) -> None:
        """Open the filter (no text)."""
        TreeFilterMixin.action_tree_filter(host)  # type: ignore[arg-type]

    def _type(self, host: _FilterHost, text: str) -> None:
        """Simulate typing `text` into the already-open filter."""
        for ch in text:
            host._tree_filter_text += ch
            TreeFilterMixin._update_tree_filter(host)  # type: ignore[arg-type]

    def _backspace(self, host: _FilterHost) -> None:
        """Simulate pressing backspace while filter is active."""
        if host._tree_filter_text:
            host._tree_filter_text = host._tree_filter_text[:-1]
            TreeFilterMixin._update_tree_filter(host)  # type: ignore[arg-type]

    def test_typing_t_filters_to_t_matches(self):
        host = _FilterHost(self.CONNECTION_NAMES)

        self._open_filter(host)
        self._type(host, "t")

        visible = set(_visible_node_names(host))
        assert visible == self.T_MATCHES, (
            f"Expected only 't'-matching connections visible, got {visible}"
        )

    def test_typing_tt_filters_out_everything(self):
        host = _FilterHost(self.CONNECTION_NAMES)

        self._open_filter(host)
        self._type(host, "tt")

        visible = _visible_node_names(host)
        assert visible == [], (
            f"Expected no connections to match 'tt', got {visible}"
        )

    def test_backspace_after_tt_restores_t_matches(self):
        """The key regression: narrowing then widening should restore matches.

        After typing 't' (matches), then 't' again ('tt', no matches),
        pressing backspace returns the query to 't' and the previously
        matching connections must reappear.
        """
        host = _FilterHost(self.CONNECTION_NAMES)

        self._open_filter(host)

        # Type 't' -> 't' matches visible
        self._type(host, "t")
        assert set(_visible_node_names(host)) == self.T_MATCHES

        # Type 't' again -> filter is 'tt', no matches
        self._type(host, "t")
        assert _visible_node_names(host) == []

        # Backspace -> filter is 't' again; 't'-matching nodes must reappear
        self._backspace(host)

        visible = set(_visible_node_names(host))
        assert visible == self.T_MATCHES, (
            "After backspacing from 'tt' back to 't', expected the "
            f"'t'-matching connections to reappear, but got {visible}"
        )

    def test_backspace_to_empty_restores_all(self):
        """Backspacing all the way clears the filter and restores every node."""
        host = _FilterHost(self.CONNECTION_NAMES)

        self._open_filter(host)
        self._type(host, "t")
        assert set(_visible_node_names(host)) == self.T_MATCHES

        self._backspace(host)

        visible = _visible_node_names(host)
        assert set(visible) == set(self.CONNECTION_NAMES)
