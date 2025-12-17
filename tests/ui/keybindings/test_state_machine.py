"""Tests for state machine action validation."""

from __future__ import annotations

from sqlit.state_machine import QueryExecutingState, UIStateMachine
from sqlit.ui.tree_nodes import ConnectionNode
from sqlit.widgets import VimMode


class MockConfig:
    name = "test-conn"


class MockNode:
    def __init__(self, data=None):
        self.data = data


class MockWidget:
    has_focus = False
    cursor_node = None
    root = MockNode()


class MockApp:
    def __init__(self):
        self._leader_pending = False
        self._query_executing = False
        self._autocomplete_visible = False
        self.current_connection = None
        self.current_config = None
        self.screen_stack = [None]
        self._vim_mode = VimMode.NORMAL

    object_tree = MockWidget()
    query_input = MockWidget()
    results_table = MockWidget()

    @property
    def vim_mode(self):
        return self._vim_mode


class TestQueryExecutingState:
    """Test that cancel_operation is only allowed when query is executing."""

    def test_cancel_not_allowed_when_idle(self):
        """cancel_operation should be blocked when no query is running."""
        sm = UIStateMachine()
        app = MockApp()
        app._query_executing = False

        assert sm.check_action(app, "cancel_operation") is False

    def test_cancel_allowed_when_query_executing(self):
        """cancel_operation should be allowed when a query is running."""
        sm = UIStateMachine()
        app = MockApp()
        app._query_executing = True

        assert sm.check_action(app, "cancel_operation") is True

    def test_active_state_is_query_executing_when_running(self):
        """Active state should be QueryExecutingState when query is running."""
        sm = UIStateMachine()
        app = MockApp()
        app._query_executing = True

        state = sm.get_active_state(app)
        assert isinstance(state, QueryExecutingState)

    def test_footer_shows_cancel_when_executing(self):
        """Footer should show cancel binding when query is executing."""
        sm = UIStateMachine()
        app = MockApp()
        app._query_executing = True

        left, right = sm.get_display_bindings(app)
        actions = [b.action for b in left]
        assert "cancel_operation" in actions


class TestStateMachineActionValidation:
    """Test that the state machine correctly validates actions."""

    def test_edit_connection_only_allowed_on_connection_node(self):
        """edit_connection should only be allowed when tree is on a connection."""
        sm = UIStateMachine()
        app = MockApp()

        # Query focused - edit_connection should be blocked
        app.query_input.has_focus = True
        app.object_tree.has_focus = False
        assert sm.check_action(app, "edit_connection") is False

        # Tree focused but not on connection - blocked
        app.query_input.has_focus = False
        app.object_tree.has_focus = True
        app.object_tree.cursor_node = MockNode(data="not_a_connection")
        assert sm.check_action(app, "edit_connection") is False

        # Tree focused on connection - allowed
        app.object_tree.cursor_node = MockNode(data=ConnectionNode(config=MockConfig()))
        assert sm.check_action(app, "edit_connection") is True
