"""Query execution mixin for SSMSTUI."""

from __future__ import annotations

from typing import Any

from textual.worker import Worker

from sqlit.shared.ui.spinner import Spinner

from .query_editing_clipboard import QueryEditingClipboardMixin
from .query_editing_comments import QueryEditingCommentsMixin
from .query_editing_common import QueryEditingCommonMixin
from .query_editing_cursor import QueryEditingCursorMixin
from .query_editing_operators import QueryEditingOperatorsMixin
from .query_editing_selection import QueryEditingSelectionMixin
from .query_editing_undo import QueryEditingUndoMixin
from .query_execution import QueryExecutionMixin
from .query_results import QueryResultsMixin


class QueryMixin(
    QueryEditingCommonMixin,
    QueryEditingUndoMixin,
    QueryEditingSelectionMixin,
    QueryEditingOperatorsMixin,
    QueryEditingClipboardMixin,
    QueryEditingCommentsMixin,
    QueryEditingCursorMixin,
    QueryExecutionMixin,
    QueryResultsMixin,
):
    """Mixin providing query execution functionality."""

    _query_service: Any | None = None
    _query_service_db_type: str | None = None
    _history_store: Any | None = None
    _query_worker: Worker[Any] | None = None
    _schema_worker: Worker[Any] | None = None
    _cancellable_query: Any | None = None
    _query_handle: Any | None = None
    _query_spinner: Spinner | None = None
    _query_cursor_cache: dict[str, tuple[int, int]] | None = None  # query text -> cursor (row, col)
    _results_table_counter: int = 0  # Counter for unique table IDs
    _results_render_worker: Worker[Any] | None = None
    _results_render_token: int = 0
    _query_target_database: str | None = None
