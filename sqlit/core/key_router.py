"""Resolve key presses to action names using core keymap + state."""

from __future__ import annotations

from collections.abc import Callable

from sqlit.core.binding_contexts import get_binding_contexts
from sqlit.core.input_context import InputContext
from sqlit.core.keymap import get_keymap
from sqlit.core.leader_commands import get_leader_commands


def resolve_action(
    key: str,
    ctx: InputContext,
    *,
    is_allowed: Callable[[str], bool],
) -> str | None:
    """Resolve a key to an action name for the given context.

    Args:
        key: The key identifier (e.g., "enter", "ctrl+q", "a").
        ctx: The current input context snapshot.
        is_allowed: Callable that checks if an action is allowed in the current state.
    """
    if ctx.leader_pending:
        for cmd in get_leader_commands(ctx.leader_menu):
            if cmd.key == key and cmd.is_allowed(ctx):
                return cmd.binding_action
        return None

    contexts = get_binding_contexts(ctx)
    keymap = get_keymap()
    for action_key in keymap.get_action_keys():
        if action_key.key != key:
            continue
        if action_key.context is not None and action_key.context not in contexts:
            continue
        if is_allowed(action_key.action):
            return action_key.action
    return None
