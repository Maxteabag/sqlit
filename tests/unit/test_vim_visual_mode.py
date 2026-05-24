"""Unit tests for visual mode selection logic and state machine wiring."""

from __future__ import annotations

from sqlit.core.binding_contexts import get_binding_contexts
from sqlit.core.input_context import InputContext
from sqlit.core.key_router import resolve_action
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


class TestBindingContexts:
    """Test that binding contexts resolve correctly for visual modes."""

    def test_visual_mode_context(self) -> None:
        ctx = make_context(focus="query", vim_mode=VimMode.VISUAL)
        contexts = get_binding_contexts(ctx)
        assert "query_visual" in contexts
        assert "query_normal" not in contexts
        assert "query_visual_line" not in contexts

    def test_visual_line_mode_context(self) -> None:
        ctx = make_context(focus="query", vim_mode=VimMode.VISUAL_LINE)
        contexts = get_binding_contexts(ctx)
        assert "query_visual_line" in contexts
        assert "query_normal" not in contexts
        assert "query_visual" not in contexts

    def test_normal_mode_context_unchanged(self) -> None:
        ctx = make_context(focus="query", vim_mode=VimMode.NORMAL)
        contexts = get_binding_contexts(ctx)
        assert "query_normal" in contexts
        assert "query_visual" not in contexts
        assert "query_visual_line" not in contexts


class TestVisualModeStateMachine:
    """Test state machine action validation for visual modes."""

    def test_enter_visual_mode_allowed_in_normal(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.NORMAL)
        assert sm.check_action(ctx, "enter_visual_mode") is True

    def test_enter_visual_line_mode_allowed_in_normal(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.NORMAL)
        assert sm.check_action(ctx, "enter_visual_line_mode") is True

    def test_enter_visual_mode_blocked_in_visual(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.VISUAL)
        assert sm.check_action(ctx, "enter_visual_mode") is False

    def test_enter_visual_line_blocked_in_visual_line(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.VISUAL_LINE)
        assert sm.check_action(ctx, "enter_visual_line_mode") is False

    def test_insert_mode_blocked_in_visual(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.VISUAL)
        assert sm.check_action(ctx, "enter_insert_mode") is False

    def test_insert_mode_blocked_in_visual_line(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.VISUAL_LINE)
        assert sm.check_action(ctx, "enter_insert_mode") is False

    def test_switch_to_visual_line_allowed_in_visual(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.VISUAL)
        assert sm.check_action(ctx, "switch_to_visual_line_mode") is True

    def test_switch_to_visual_allowed_in_visual_line(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.VISUAL_LINE)
        assert sm.check_action(ctx, "switch_to_visual_mode") is True


class TestVisualModeOperatorActions:
    """Test that operators are allowed in visual modes and blocked elsewhere."""

    def test_visual_operators_allowed(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.VISUAL)
        for action in ["visual_yank", "visual_delete", "visual_change", "visual_execute"]:
            assert sm.check_action(ctx, action) is True, f"{action} should be allowed"

    def test_visual_line_operators_allowed(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.VISUAL_LINE)
        for action in ["visual_line_yank", "visual_line_delete", "visual_line_change", "visual_line_execute"]:
            assert sm.check_action(ctx, action) is True, f"{action} should be allowed"

    def test_leader_operators_blocked_in_visual(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.VISUAL)
        for action in ["delete_leader_key", "yank_leader_key", "change_leader_key"]:
            assert sm.check_action(ctx, action) is False, f"{action} should be blocked"

    def test_leader_operators_blocked_in_visual_line(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.VISUAL_LINE)
        for action in ["delete_leader_key", "yank_leader_key", "change_leader_key"]:
            assert sm.check_action(ctx, action) is False, f"{action} should be blocked"


class TestVisualModeMotionActions:
    """Test that motions are allowed in the correct visual modes."""

    def test_all_motions_allowed_in_visual(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.VISUAL)
        motions = [
            "cursor_left", "cursor_right", "cursor_up", "cursor_down",
            "cursor_word_forward", "cursor_word_back",
            "cursor_line_start", "cursor_line_end", "cursor_last_line",
            "cursor_matching_bracket", "cursor_find_char", "cursor_find_char_back",
        ]
        for action in motions:
            assert sm.check_action(ctx, action) is True, f"{action} should be allowed"

    def test_vertical_motions_allowed_in_visual_line(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.VISUAL_LINE)
        for action in ["cursor_up", "cursor_down", "cursor_last_line", "g_leader_key", "g_first_line"]:
            assert sm.check_action(ctx, action) is True, f"{action} should be allowed"


class TestVisualModeKeyRouting:
    """Test that keys resolve to correct actions in visual modes."""

    def test_visual_mode_key_routing(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.VISUAL)
        is_allowed = lambda name: sm.check_action(ctx, name)

        expected = {
            "h": "cursor_left",
            "j": "cursor_down",
            "k": "cursor_up",
            "l": "cursor_right",
            "w": "cursor_word_forward",
            "b": "cursor_word_back",
            "y": "visual_yank",
            "d": "visual_delete",
            "c": "visual_change",
            "V": "switch_to_visual_line_mode",
            "escape": "exit_visual_mode",
            "enter": "visual_execute",
        }
        for key, action in expected.items():
            result = resolve_action(key, ctx, is_allowed=is_allowed)
            assert result == action, f"key '{key}' should resolve to '{action}', got '{result}'"

    def test_visual_line_mode_key_routing(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.VISUAL_LINE)
        is_allowed = lambda name: sm.check_action(ctx, name)

        expected = {
            "j": "cursor_down",
            "k": "cursor_up",
            "G": "cursor_last_line",
            "y": "visual_line_yank",
            "d": "visual_line_delete",
            "c": "visual_line_change",
            "v": "switch_to_visual_mode",
            "escape": "exit_visual_line_mode",
            "enter": "visual_line_execute",
        }
        for key, action in expected.items():
            result = resolve_action(key, ctx, is_allowed=is_allowed)
            assert result == action, f"key '{key}' should resolve to '{action}', got '{result}'"

    def test_normal_mode_entry_keys(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.NORMAL)
        is_allowed = lambda name: sm.check_action(ctx, name)

        assert resolve_action("v", ctx, is_allowed=is_allowed) == "enter_visual_mode"
        assert resolve_action("V", ctx, is_allowed=is_allowed) == "enter_visual_line_mode"


class TestVisualModeFooterBindings:
    """Test that footer displays correct bindings in visual modes."""

    def test_visual_mode_footer(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.VISUAL)
        left, _ = sm.get_display_bindings(ctx)
        actions = {b.action for b in left}
        assert "exit_visual_mode" in actions
        assert "visual_yank" in actions
        assert "visual_delete" in actions
        assert "visual_change" in actions
        assert "visual_execute" in actions

    def test_visual_line_mode_footer(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.VISUAL_LINE)
        left, _ = sm.get_display_bindings(ctx)
        actions = {b.action for b in left}
        assert "exit_visual_line_mode" in actions
        assert "visual_line_yank" in actions
        assert "visual_line_delete" in actions
        assert "visual_line_change" in actions
        assert "visual_line_execute" in actions
