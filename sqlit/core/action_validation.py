"""Validate keymap and leader actions against the app surface."""

from __future__ import annotations

from typing import Any

from sqlit.core.keymap import get_keymap
from sqlit.core.leader_commands import get_leader_commands


def validate_actions(app: Any) -> list[str]:
    missing: set[str] = set()

    for action_key in get_keymap().get_action_keys():
        action_name = f"action_{action_key.action}"
        if not hasattr(app, action_name):
            missing.add(action_name)

    for menu in ("leader", "delete", "yank", "change"):
        for cmd in get_leader_commands(menu):
            action_name = f"action_{cmd.binding_action}"
            if not hasattr(app, action_name):
                missing.add(action_name)

    return sorted(missing)
