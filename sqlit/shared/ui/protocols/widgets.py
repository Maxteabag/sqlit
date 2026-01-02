"""Protocol for top-level widget accessors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from textual.widgets import Static, TextArea, Tree

    from sqlit.shared.ui.widgets import SqlitDataTable


class WidgetAccessProtocol(Protocol):
    @property
    def object_tree(self) -> Tree[Any]:
        ...

    @property
    def query_input(self) -> TextArea:
        ...

    @property
    def results_table(self) -> SqlitDataTable:
        ...

    @property
    def status_bar(self) -> Static:
        ...

    @property
    def autocomplete_dropdown(self) -> Any:
        ...

    @property
    def tree_filter_input(self) -> Any:
        ...

    @property
    def results_filter_input(self) -> Any:
        ...

    @property
    def results_area(self) -> Any:
        ...
