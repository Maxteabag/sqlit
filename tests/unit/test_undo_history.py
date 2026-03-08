"""Tests for the UndoHistory class."""

from sqlit.domains.query.editing import UndoHistory


class TestUndoHistory:
    """Tests for UndoHistory."""

    def test_initial_state(self) -> None:
        """History starts empty."""
        history = UndoHistory()
        assert not history.can_undo()
        assert not history.can_redo()
        assert history.current is None

    def test_push_single_state(self) -> None:
        """Pushing a state makes it current."""
        history = UndoHistory()
        history.push("hello", 0, 5)

        assert history.current is not None
        assert history.current.text == "hello"
        assert history.current.cursor_row == 0
        assert history.current.cursor_col == 5
        assert not history.can_undo()  # Only one state
        assert not history.can_redo()

    def test_push_multiple_states(self) -> None:
        """Pushing multiple states enables undo."""
        history = UndoHistory()
        history.push("hello", 0, 5)
        history.push("hello world", 0, 11)

        assert history.current is not None
        assert history.current.text == "hello world"
        assert history.can_undo()
        assert not history.can_redo()

    def test_undo(self) -> None:
        """Undo returns previous state."""
        history = UndoHistory()
        history.push("hello", 0, 5)
        history.push("hello world", 0, 11)

        state = history.undo()

        assert state is not None
        assert state.text == "hello"
        assert state.cursor_row == 0
        assert state.cursor_col == 5
        assert history.current == state
        assert not history.can_undo()
        assert history.can_redo()

    def test_redo(self) -> None:
        """Redo returns next state after undo."""
        history = UndoHistory()
        history.push("hello", 0, 5)
        history.push("hello world", 0, 11)
        history.undo()

        state = history.redo()

        assert state is not None
        assert state.text == "hello world"
        assert history.can_undo()
        assert not history.can_redo()

    def test_new_edit_clears_redo(self) -> None:
        """New edit after undo clears redo stack."""
        history = UndoHistory()
        history.push("hello", 0, 5)
        history.push("hello world", 0, 11)
        history.undo()

        # This new edit should clear the redo stack
        history.push("hello there", 0, 11)

        assert not history.can_redo()
        assert history.current is not None
        assert history.current.text == "hello there"

    def test_duplicate_states_ignored(self) -> None:
        """Pushing identical text doesn't create new undo entry."""
        history = UndoHistory()
        history.push("hello", 0, 0)
        history.push("hello", 0, 5)  # Same text, different cursor

        assert not history.can_undo()  # No undo because text is the same

    def test_max_size_limit(self) -> None:
        """History respects max size limit."""
        history = UndoHistory(max_size=3)

        # Push 5 different states
        for i in range(5):
            history.push(f"text{i}", 0, i)

        # Should only be able to undo 3 times (max_size)
        undo_count = 0
        while history.can_undo():
            history.undo()
            undo_count += 1

        assert undo_count == 3

    def test_undo_empty_history(self) -> None:
        """Undo on empty history returns None."""
        history = UndoHistory()
        assert history.undo() is None

    def test_redo_empty_stack(self) -> None:
        """Redo with empty redo stack returns None."""
        history = UndoHistory()
        history.push("hello", 0, 5)
        assert history.redo() is None

    def test_clear(self) -> None:
        """Clear removes all history."""
        history = UndoHistory()
        history.push("hello", 0, 5)
        history.push("hello world", 0, 11)

        history.clear()

        assert not history.can_undo()
        assert not history.can_redo()
        assert history.current is None

    def test_multiple_undo_redo(self) -> None:
        """Multiple undo/redo operations work correctly."""
        history = UndoHistory()
        history.push("a", 0, 1)
        history.push("ab", 0, 2)
        history.push("abc", 0, 3)

        # Undo twice
        history.undo()
        history.undo()
        assert history.current is not None
        assert history.current.text == "a"

        # Redo once
        history.redo()
        assert history.current is not None
        assert history.current.text == "ab"

        # Undo once more
        history.undo()
        assert history.current is not None
        assert history.current.text == "a"

        # Redo twice
        history.redo()
        history.redo()
        assert history.current is not None
        assert history.current.text == "abc"
