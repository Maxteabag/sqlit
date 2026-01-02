"""Resolve active keybinding contexts from the input context."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.vim import VimMode


def get_binding_contexts(ctx: InputContext) -> set[str]:
    """Determine which keybinding contexts should be active."""
    contexts = {"global", "navigation"}

    if ctx.focus == "explorer":
        contexts.add("tree")
    if ctx.tree_filter_active:
        contexts.add("tree_filter")

    if ctx.focus == "query":
        contexts.add("query")
        if ctx.vim_mode == VimMode.INSERT:
            contexts.add("query_insert")
        else:
            contexts.add("query_normal")
    if ctx.autocomplete_visible:
        contexts.add("autocomplete")

    if ctx.focus == "results":
        contexts.add("results")
    if ctx.results_filter_active:
        contexts.add("results_filter")
    if ctx.value_view_active:
        contexts.add("value_view")

    return contexts
