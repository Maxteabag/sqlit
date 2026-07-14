"""Tests for Tab behavior in the query editor."""

from __future__ import annotations

from sqlit.core.binding_contexts import get_binding_contexts
from sqlit.core.input_context import InputContext
from sqlit.core.key_router import resolve_action
from sqlit.core.vim import VimMode
from sqlit.domains.shell.state import UIStateMachine
from sqlit.shared.ui.widgets_text_area import QueryTextArea


def make_context(**overrides: object) -> InputContext:
    """Build a default InputContext with optional overrides."""
    data = {
        "focus": "query",
        "vim_mode": VimMode.INSERT,
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


class TestTabKeyRouting:
    """Tab should indent in insert mode, but accept autocomplete when open."""

    def _is_allowed(self, ctx: InputContext, name: str) -> bool:
        sm = UIStateMachine()
        return sm.check_action(ctx, name)

    def test_tab_in_insert_mode_without_autocomplete_is_unresolved(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.INSERT, autocomplete_visible=False)

        assert resolve_action("tab", ctx, is_allowed=lambda name: sm.check_action(ctx, name)) is None

    def test_tab_in_insert_mode_with_autocomplete_accepts(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.INSERT, autocomplete_visible=True)

        assert resolve_action("tab", ctx, is_allowed=lambda name: sm.check_action(ctx, name)) == "autocomplete_accept"

    def test_tab_in_normal_mode_is_unresolved(self) -> None:
        sm = UIStateMachine()
        ctx = make_context(focus="query", vim_mode=VimMode.NORMAL, autocomplete_visible=False)

        assert resolve_action("tab", ctx, is_allowed=lambda name: sm.check_action(ctx, name)) is None

    def test_autocomplete_context_only_active_when_visible(self) -> None:
        ctx_hidden = make_context(focus="query", vim_mode=VimMode.INSERT, autocomplete_visible=False)
        ctx_visible = make_context(focus="query", vim_mode=VimMode.INSERT, autocomplete_visible=True)

        assert "autocomplete" not in get_binding_contexts(ctx_hidden)
        assert "autocomplete" in get_binding_contexts(ctx_visible)


class TestQueryTextAreaTabBehavior:
    """QueryTextArea keeps focus-friendly tab behavior but inserts real tabs."""

    def test_query_text_area_keeps_focus_tab_behavior(self) -> None:
        ta = QueryTextArea()
        assert ta.tab_behavior == "focus"

    def test_query_text_area_uses_tab_characters(self) -> None:
        ta = QueryTextArea()
        assert ta.indent_type == "tabs"

    def test_query_text_area_tab_insert_string(self) -> None:
        ta = QueryTextArea()
        assert ta._tab_insert_string() == "\t"
