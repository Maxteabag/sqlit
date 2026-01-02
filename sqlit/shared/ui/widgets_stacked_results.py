"""Stacked results container for multi-statement queries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pyarrow as pa
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Collapsible, Static
from textual_fastdatatable import ArrowBackend

from .widgets_tables import SqlitDataTable

if TYPE_CHECKING:
    from sqlit.domains.query.app.multi_statement import StatementResult
    from sqlit.domains.query.app.query_service import QueryResult

# Maximum characters for statement in title
MAX_STATEMENT_TITLE_LENGTH = 60
# Maximum rows to show in each result table
MAX_ROWS_PER_RESULT = 100
# Auto-collapse threshold
AUTO_COLLAPSE_THRESHOLD = 5


class ErrorDisplay(Static):
    """Inline error display for failed statements."""

    DEFAULT_CSS = """
    ErrorDisplay {
        background: $error 15%;
        color: $error;
        padding: 1;
        margin: 0;
    }
    """

    def __init__(self, error_message: str) -> None:
        super().__init__(error_message)


class NonQueryDisplay(Static):
    """Display for INSERT/UPDATE/DELETE showing rows affected."""

    DEFAULT_CSS = """
    NonQueryDisplay {
        padding: 1;
        color: $text-muted;
    }
    """

    def __init__(self, rows_affected: int) -> None:
        if rows_affected == 1:
            text = "1 row affected"
        elif rows_affected == -1:
            text = "Query executed successfully"
        else:
            text = f"{rows_affected} rows affected"
        super().__init__(text)


class ResultSection(Collapsible):
    """Collapsible section for one statement result."""

    DEFAULT_CSS = """
    ResultSection {
        margin-bottom: 1;
        padding: 0;
    }

    ResultSection.-collapsed {
        height: auto;
    }

    ResultSection CollapsibleTitle {
        padding: 0 1;
    }

    ResultSection.error CollapsibleTitle {
        color: $error;
    }

    ResultSection.success CollapsibleTitle {
        color: $success;
    }

    ResultSection DataTable {
        /* Height is set dynamically based on row count */
        margin-right: 1;
    }
    """

    def __init__(
        self,
        statement: str,
        index: int,
        *,
        content: Any = None,
        is_error: bool = False,
        collapsed: bool = False,
    ) -> None:
        title = self._format_title(statement, index, is_error)
        super().__init__(title=title, collapsed=collapsed)
        self.statement = statement
        self.index = index
        self.is_error = is_error
        self.result_columns: list[str] = []
        self.result_rows: list[tuple] = []
        self._content = content
        if is_error:
            self.add_class("error")
        else:
            self.add_class("success")

    def compose(self) -> ComposeResult:
        """Yield the content widget."""
        if self._content is not None:
            yield self._content

    def _format_title(self, statement: str, index: int, is_error: bool) -> str:
        """Format the collapsible title."""
        # Clean up statement for display
        stmt_display = " ".join(statement.split())  # Normalize whitespace
        if len(stmt_display) > MAX_STATEMENT_TITLE_LENGTH:
            stmt_display = stmt_display[: MAX_STATEMENT_TITLE_LENGTH - 3] + "..."

        prefix = "ERROR" if is_error else f"#{index + 1}"
        return f"[{prefix}] {stmt_display}"


class StackedResultsContainer(VerticalScroll):
    """Container for multiple stacked query results."""

    DEFAULT_CSS = """
    StackedResultsContainer {
        height: 1fr;
        display: none;
    }

    StackedResultsContainer.active {
        display: block;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._section_count = 0

    def clear_results(self) -> None:
        """Remove all result sections."""
        for child in list(self.children):
            child.remove()
        self._section_count = 0

    def add_result_section(
        self,
        stmt_result: StatementResult,
        index: int,
        *,
        auto_collapse: bool = False,
    ) -> None:
        """Add a result section for a statement result."""
        from sqlit.domains.query.app.query_service import QueryResult

        # Build the content widget first
        content: SqlitDataTable | NonQueryDisplay | ErrorDisplay
        result_columns: list[str] = []
        result_rows: list[tuple] = []
        if stmt_result.success and stmt_result.result is not None:
            if isinstance(stmt_result.result, QueryResult):
                # SELECT result - build a DataTable
                result_columns, result_rows = self._get_result_table_data(stmt_result.result)
                content = self._build_result_table_from_rows(result_columns, result_rows, index)
            else:
                # Non-query result (INSERT/UPDATE/DELETE)
                content = NonQueryDisplay(stmt_result.result.rows_affected)
        else:
            # Error result
            error_msg = stmt_result.error or "Unknown error"
            content = ErrorDisplay(error_msg)

        section = ResultSection(
            stmt_result.statement,
            index,
            content=content,
            is_error=not stmt_result.success,
            collapsed=auto_collapse,
        )
        section.result_columns = result_columns
        section.result_rows = result_rows

        self.mount(section)
        self._section_count += 1

    def _get_result_table_data(self, result: QueryResult) -> tuple[list[str], list[tuple]]:
        """Normalize QueryResult into columns/rows for display."""
        columns = result.columns or ["Result"]
        rows = result.rows or []

        # Limit rows for performance
        if len(rows) > MAX_ROWS_PER_RESULT:
            rows = rows[:MAX_ROWS_PER_RESULT]

        if not columns:
            columns = ["(empty)"]
            rows = []

        return columns, rows

    def _build_result_table_from_rows(
        self, columns: list[str], rows: list[tuple], index: int
    ) -> SqlitDataTable:
        """Build a DataTable for a QueryResult."""
        # Convert rows to column-oriented format
        column_data: dict[str, list[Any]] = {col: [] for col in columns}
        for row in rows:
            for i, col in enumerate(columns):
                val = row[i] if i < len(row) else None
                # Convert to string for display
                column_data[col].append(str(val) if val is not None else "NULL")

        arrow_table = pa.table(column_data)
        backend = ArrowBackend(arrow_table)

        # Calculate height: 1 for header + number of rows, capped at 15
        table_height = min(1 + len(rows), 15)

        table = SqlitDataTable(
            id=f"result-table-{index}",
            zebra_stripes=True,
            backend=backend,
        )
        table.styles.height = table_height
        return table

    @property
    def section_count(self) -> int:
        """Number of result sections."""
        return self._section_count

    def get_section(self, index: int) -> ResultSection | None:
        """Get a result section by index."""
        sections = list(self.query(ResultSection))
        if 0 <= index < len(sections):
            return sections[index]
        return None

    def collapse_all(self) -> None:
        """Collapse all sections."""
        for section in self.query(ResultSection):
            section.collapsed = True

    def expand_all(self) -> None:
        """Expand all sections."""
        for section in self.query(ResultSection):
            section.collapsed = False
