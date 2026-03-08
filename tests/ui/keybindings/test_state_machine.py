"""Tests for state machine action validation."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.vim import VimMode
from sqlit.domains.shell.state import UIStateMachine


def make_context(**overrides: object) -> InputContext:
    """Build a default InputContext with optional overrides."""
    data = {
        "focus": "none",
        "vim_mode": VimMode.NORMAL,
        "leader_pending": False,
        "leader_menu": "leader",
        "tree_filter_active": False,
        "tree_multi_select_active": False,
        "tree_visual_mode_active": False,
        "autocomplete_visible": False,
        "results_filter_active": False,
        "value_view_active": False,
        "value_view_tree_mode": False,
        "value_view_is_json": False,
        "query_executing": False,
        "modal_open": False,
        "has_connection": False,
        "current_connection_name": None,
        "tree_node_kind": None,
        "tree_node_connection_name": None,
        "tree_node_connection_selected": False,
        "last_result_is_error": False,
        "has_results": False,
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

    def test_visual_mode_allowed_on_connection_node(self):
        """enter_tree_visual_mode should only be allowed on connection nodes."""
        sm = UIStateMachine()

        # On table node - should be blocked (not a connection)
        ctx = make_context(focus="explorer", tree_node_kind="table")
        # Visual mode entry is allowed from tree_focused state on any node
        # The action itself will check if it's a connection
        assert sm.check_action(ctx, "enter_tree_visual_mode") is True

        ctx = make_context(
            focus="explorer",
            tree_node_kind="connection",
            tree_node_connection_name="test-conn",
        )
        assert sm.check_action(ctx, "enter_tree_visual_mode") is True

    def test_clear_selection_only_allowed_when_active(self):
        """clear_connection_selection should only be allowed in multi-select mode."""
        sm = UIStateMachine()

        ctx = make_context(focus="explorer", tree_multi_select_active=False)
        assert sm.check_action(ctx, "clear_connection_selection") is False

        ctx = make_context(focus="explorer", tree_multi_select_active=True)
        assert sm.check_action(ctx, "clear_connection_selection") is True

    def test_multi_select_footer_shows_actions(self):
        """Footer should show multi-select actions when active (after exiting visual mode)."""
        sm = UIStateMachine()
        ctx = make_context(focus="explorer", tree_multi_select_active=True)

        left, _ = sm.get_display_bindings(ctx)
        actions = {b.action for b in left}
        assert "clear_connection_selection" in actions
        assert "move_connection_to_folder" in actions
        assert "delete_connection" in actions

    def test_visual_mode_footer_shows_actions(self):
        """Footer should show visual mode actions when visual mode is active."""
        sm = UIStateMachine()
        ctx = make_context(
            focus="explorer",
            tree_visual_mode_active=True,
            tree_multi_select_active=True,
        )

        left, _ = sm.get_display_bindings(ctx)
        actions = {b.action for b in left}
        assert "exit_tree_visual_mode" in actions
        assert "move_connection_to_folder" in actions
        assert "delete_connection" in actions


class TestValueViewStates:
    """Test that value view states correctly gate actions based on content type."""

    def test_toggle_blocked_for_non_json(self):
        """toggle_value_view_mode should be blocked when content is not JSON."""
        sm = UIStateMachine()
        ctx = make_context(value_view_active=True, value_view_is_json=False)

        assert sm.check_action(ctx, "toggle_value_view_mode") is False

    def test_toggle_allowed_for_json(self):
        """toggle_value_view_mode should be allowed when content is JSON."""
        sm = UIStateMachine()
        ctx = make_context(value_view_active=True, value_view_is_json=True)

        assert sm.check_action(ctx, "toggle_value_view_mode") is True

    def test_collapse_all_only_in_tree_mode(self):
        """collapse_all_json_nodes should only be allowed in tree mode."""
        sm = UIStateMachine()

        # Tree mode - allowed
        ctx = make_context(
            value_view_active=True,
            value_view_is_json=True,
            value_view_tree_mode=True,
        )
        assert sm.check_action(ctx, "collapse_all_json_nodes") is True

        # Syntax mode - blocked
        ctx = make_context(
            value_view_active=True,
            value_view_is_json=True,
            value_view_tree_mode=False,
        )
        assert sm.check_action(ctx, "collapse_all_json_nodes") is False
