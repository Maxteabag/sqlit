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

from sqlit.domains.explorer.domain.tree_nodes import (
    ConnectionNode,
    DatabaseNode,
    FolderNode,
    TableNode,
)
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


class _MultiDbFilterHost(TreeFilterMixin):
    """Filter host that models multi-database 'browse all' mode.

    The tree starts shaped like a real session after the user has expanded
    into one database's Tables folder:

        connection
        └── Databases
            ├── CS         (expanded — tables already loaded)
            │   └── Tables
            │       ├── cs_user
            │       ├── cs_session
            │       └── cs_ticket
            └── Sales      (collapsed — lazy-loaded if expanded)

    `refresh_tree` here mirrors the real `refresh_tree_incremental`: it
    rebuilds the connection + Databases + database nodes synchronously,
    but the contents of the Tables folder are reloaded asynchronously and
    are *not* present when refresh_tree returns. This is what produces
    issue #141 — opening the filter calls refresh_tree, the lazy-loaded
    tables vanish, and the subsequent filter search finds nothing.
    """

    def __init__(
        self,
        connection_name: str,
        databases: list[str],
        tables_by_db: dict[str, list[str]],
    ):
        self._connection_name = connection_name
        self._databases = databases
        self._tables_by_db = tables_by_db
        self.object_tree = MockTree()
        self.tree_filter_input = MockFilterInput()
        self._populate(include_lazy_children=True)

    def _populate(self, *, include_lazy_children: bool) -> None:
        self.object_tree.root.children = []
        config = MagicMock()
        config.name = self._connection_name
        conn_node = object.__new__(ConnectionNode)
        object.__setattr__(conn_node, "config", config)
        conn = self.object_tree.root.add(self._connection_name, data=conn_node)
        conn.allow_expand = True
        conn.is_expanded = True

        dbs_folder = conn.add("Databases", data=FolderNode(folder_type="databases"))
        dbs_folder.allow_expand = True
        dbs_folder.is_expanded = True

        for db_name in self._databases:
            db_node = dbs_folder.add(db_name, data=DatabaseNode(name=db_name))
            db_node.allow_expand = True
            if db_name not in self._tables_by_db:
                continue
            db_node.is_expanded = True
            tables_folder = db_node.add(
                "Tables",
                data=FolderNode(folder_type="tables", database=db_name),
            )
            tables_folder.allow_expand = True
            tables_folder.is_expanded = True

            # Real refresh_tree only restores the shell here. The Tables
            # folder gets re-expanded asynchronously and its children
            # don't materialize before _update_tree_filter runs.
            if include_lazy_children:
                for table in self._tables_by_db[db_name]:
                    leaf = tables_folder.add(
                        table,
                        data=TableNode(database=db_name, schema="", name=table),
                    )
                    leaf.allow_expand = True

    def refresh_tree(self) -> None:
        # Match the real behavior: shell only, lazy children absent.
        self._populate(include_lazy_children=False)

    def _update_footer_bindings(self) -> None:
        pass

    def _activate_tree_node(self, _node) -> None:
        pass


class TestMultiDbFilterIssue141:
    """Regression tests for issue #141.

    When sqlit is connected in multi-database 'browse all' mode and the
    user has expanded into a database's Tables folder, opening `/` and
    typing a substring of a table name should find that table. It
    currently returns zero matches because `_update_tree_filter` calls
    `refresh_tree`, which tears down the tree and re-expands lazy folders
    asynchronously — the search runs before the tables are reloaded.
    """

    def _open_filter(self, host: _MultiDbFilterHost) -> None:
        TreeFilterMixin.action_tree_filter(host)  # type: ignore[arg-type]

    def _type(self, host: _MultiDbFilterHost, text: str) -> None:
        for ch in text:
            host._tree_filter_text += ch
            TreeFilterMixin._update_tree_filter(host)  # type: ignore[arg-type]

    def _matched_names(self, host: _MultiDbFilterHost) -> list[str]:
        names: list[str] = []
        for node in host._tree_filter_matches:
            data = node.data
            if data is not None and hasattr(data, "get_label_text"):
                names.append(data.get_label_text())
        return sorted(names)

    def test_filter_finds_lazy_loaded_tables_in_multi_db_mode(self):
        host = _MultiDbFilterHost(
            connection_name="prod",
            databases=["CS", "Sales"],
            tables_by_db={"CS": ["cs_user", "cs_session", "cs_ticket"]},
        )

        # Sanity check: before we open the filter, the tables are present.
        cs_node = host.object_tree.root.children[0].children[0].children[0]
        tables_folder = cs_node.children[0]
        assert sorted(c.label for c in tables_folder.children) == [
            "cs_session",
            "cs_ticket",
            "cs_user",
        ]

        self._open_filter(host)
        self._type(host, "cs")

        matched = self._matched_names(host)
        # "cs" matches the CS database node itself plus its tables.
        # Issue #141: without the fix, only "CS" would be in the list
        # because refresh_tree had wiped the lazy-loaded table nodes.
        assert "cs_user" in matched
        assert "cs_session" in matched
        assert "cs_ticket" in matched, (
            f"Issue #141: filter must find lazy-loaded tables; got {matched}"
        )
