"""Tests for state machine action validation."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.vim import VimMode
from sqlit.domains.shell.state import QueryExecutingState, UIStateMachine


def make_context(**overrides: object) -> InputContext:
    """Build a default InputContext with optional overrides."""
    data = {
        "focus": "none",
        "vim_mode": VimMode.NORMAL,
        "leader_pending": False,
        "leader_menu": "leader",
        "tree_filter_active": False,
        "autocomplete_visible": False,
        "results_filter_active": False,
        "value_view_active": False,
        "query_executing": False,
        "modal_open": False,
        "has_connection": False,
        "current_connection_name": None,
        "tree_node_kind": None,
        "tree_node_connection_name": None,
        "last_result_is_error": False,
    }
    data.update(overrides)
    return InputContext(**data)


class TestQueryExecutingState:
    """Test that cancel_operation is only allowed when query is executing."""

    def test_cancel_not_allowed_when_idle(self):
        """cancel_operation should be blocked when no query is running."""
        sm = UIStateMachine()
        ctx = make_context(query_executing=False)

        assert sm.check_action(ctx, "cancel_operation") is False

    def test_cancel_allowed_when_query_executing(self):
        """cancel_operation should be allowed when a query is running."""
        sm = UIStateMachine()
        ctx = make_context(query_executing=True)

        assert sm.check_action(ctx, "cancel_operation") is True

    def test_active_state_is_query_executing_when_running(self):
        """Active state should be QueryExecutingState when query is running."""
        sm = UIStateMachine()
        ctx = make_context(query_executing=True)

        state = sm.get_active_state(ctx)
        assert isinstance(state, QueryExecutingState)

    def test_footer_shows_cancel_when_executing(self):
        """Footer should show cancel binding when query is executing."""
        sm = UIStateMachine()
        ctx = make_context(query_executing=True)

        left, right = sm.get_display_bindings(ctx)
        actions = [b.action for b in left]
        assert "cancel_operation" in actions


class TestStateMachineActionValidation:
    """Test that the state machine correctly validates actions."""

    def test_edit_connection_only_allowed_on_connection_node(self):
        """edit_connection should only be allowed when tree is on a connection."""
        sm = UIStateMachine()
        ctx = make_context()

        # Query focused - edit_connection should be blocked
        ctx = make_context(focus="query")
        assert sm.check_action(ctx, "edit_connection") is False

        # Tree focused but not on connection - blocked
        ctx = make_context(focus="explorer", tree_node_kind="table")
        assert sm.check_action(ctx, "edit_connection") is False

        # Tree focused on connection - allowed
        ctx = make_context(
            focus="explorer",
            tree_node_kind="connection",
            tree_node_connection_name="test-conn",
        )
        assert sm.check_action(ctx, "edit_connection") is True
