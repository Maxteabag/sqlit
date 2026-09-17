"""Regression coverage for CR-only text reaching autocomplete."""

from sqlit.domains.query.ui.mixins.autocomplete import AutocompleteMixin


class _QueryInput:
    def __init__(self, text: str, cursor_location: tuple[int, int]) -> None:
        self.text = text
        self.cursor_location = cursor_location


class _Dropdown:
    def __init__(self, selected: str = "FROM") -> None:
        self.selected = selected

    def get_selected(self) -> str:
        return self.selected

    def hide(self) -> None:
        pass


class _Host(AutocompleteMixin):
    def __init__(
        self,
        text: str,
        cursor_location: tuple[int, int],
        selected: str = "FROM",
    ) -> None:
        self.query_input = _QueryInput(text, cursor_location)
        self.autocomplete_dropdown = _Dropdown(selected)
        self._autocomplete_visible = True


def test_apply_autocomplete_after_cr_only_line_break() -> None:
    """A completion after CR-only text replaces only the current word."""
    host = _Host("SELECT\rONE\rFR", (2, 2))

    host._apply_autocomplete()

    assert host.query_input.text == "SELECT\rONE\rFROM"
    assert host.query_input.cursor_location == (2, 4)


def test_apply_autocomplete_preserves_non_ascii_identifier_whitespace() -> None:
    """Only SQL separators, not every Unicode whitespace, delimit identifiers."""
    identifier = "foo\N{NO-BREAK SPACE}bar"
    partial = "foo\N{NO-BREAK SPACE}b"
    host = _Host(partial, (0, len(partial)), selected=identifier)

    host._apply_autocomplete()

    assert host.query_input.text == identifier
