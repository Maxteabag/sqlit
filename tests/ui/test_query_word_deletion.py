"""UI tests for word deletion in the query editor."""

from textual.app import App, ComposeResult

from sqlit.core.vim import VimMode
from sqlit.shared.ui.widgets_text_area import QueryTextArea


class QueryWordDeletionApp(App[None]):
    """Minimal app hosting a query editor in insert mode."""

    vim_mode = VimMode.INSERT

    def compose(self) -> ComposeResult:
        yield QueryTextArea("SELECT column_name FROM users", id="query-input")


async def test_ctrl_delete_deletes_word_to_the_right() -> None:
    """Ctrl+Delete removes the word at the query cursor."""
    app = QueryWordDeletionApp()

    async with app.run_test() as pilot:
        query_input = app.query_one("#query-input", QueryTextArea)
        query_input.cursor_location = (0, 7)

        await pilot.press("ctrl+delete")

        assert query_input.text == "SELECT  FROM users"
        assert query_input.cursor_location == (0, 7)
