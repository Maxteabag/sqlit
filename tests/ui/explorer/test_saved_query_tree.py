"""Explorer representation of saved query files."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from sqlit.domains.explorer.ui.tree.builder import add_saved_query_nodes
from sqlit.domains.query.store.saved_queries import SavedQueryStore


class _Host:
    def __init__(self, store: SavedQueryStore) -> None:
        self.current_config = SimpleNamespace(name="production")
        self.services = SimpleNamespace(saved_query_store=store)


class _Node:
    def __init__(self, label: str) -> None:
        self.label = label
        self.data = None
        self.children: list[_Node] = []
        self.allow_expand = False

    def add(self, label: str) -> _Node:
        child = _Node(label)
        self.children.append(child)
        return child

    def add_leaf(self, label: str) -> _Node:
        return self.add(label)


def test_saved_queries_are_nested_under_connection_tree(tmp_path: Path) -> None:
    store = SavedQueryStore(tmp_path / "saved-queries")
    store.save("production", "reports/daily", "SELECT 1")
    store.save("production", "health", "SELECT 2")
    host = _Host(store)
    root = _Node("production")

    add_saved_query_nodes(host, root)  # type: ignore[arg-type]

    saved = root.children[0]
    assert str(saved.label) == "Saved Queries"
    assert saved.data.get_node_kind() == "saved_query_folder"
    assert [child.data.get_node_kind() for child in saved.children] == [
        "saved_query_file",
        "saved_query_folder",
    ]
    reports = saved.children[1]
    assert reports.data.relative_path == "reports"
    assert reports.children[0].data.entry.relative_path == "reports/daily.sql"


def test_no_saved_query_folder_before_first_save(tmp_path: Path) -> None:
    store = SavedQueryStore(tmp_path / "saved-queries")
    host = _Host(store)
    root = _Node("production")

    add_saved_query_nodes(host, root)  # type: ignore[arg-type]

    assert root.children == []
