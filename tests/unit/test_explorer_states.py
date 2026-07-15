"""Unit tests for explorer tree state detection."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.vim import VimMode
from sqlit.domains.explorer.state.tree_on_object import TreeOnObjectState


def _context(tree_node_kind: str | None) -> InputContext:
    return InputContext(
        focus="explorer",
        vim_mode=VimMode.NORMAL,
        leader_pending=False,
        leader_menu="",
        tree_filter_active=False,
        tree_multi_select_active=False,
        tree_visual_mode_active=False,
        autocomplete_visible=False,
        results_filter_active=False,
        value_view_active=False,
        value_view_tree_mode=False,
        value_view_is_json=False,
        query_executing=False,
        modal_open=False,
        has_connection=True,
        current_connection_name="test",
        tree_node_kind=tree_node_kind,
        tree_node_connection_name=None,
        tree_node_connection_selected=False,
        last_result_is_error=False,
        has_results=False,
    )


def test_tree_on_object_state_is_active_for_procedure() -> None:
    """Procedure nodes are treated as object nodes for key bindings."""
    state = TreeOnObjectState()
    assert state.is_active(_context("procedure")) is True


def test_tree_on_object_state_is_active_for_index_trigger_sequence() -> None:
    """Index, trigger, and sequence nodes are still object nodes."""
    state = TreeOnObjectState()
    assert state.is_active(_context("index")) is True
    assert state.is_active(_context("trigger")) is True
    assert state.is_active(_context("sequence")) is True


def test_tree_on_object_state_is_inactive_for_table_view() -> None:
    """Table and view nodes use a different state."""
    state = TreeOnObjectState()
    assert state.is_active(_context("table")) is False
    assert state.is_active(_context("view")) is False
