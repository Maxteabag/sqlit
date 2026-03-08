"""Shared fixtures and mocks for keybindings tests."""

from __future__ import annotations

import pytest

from sqlit.core.keymap import (
    ActionKeyDef,
    KeymapProvider,
    LeaderCommandDef,
    reset_keymap,
)


class MockKeymapProvider(KeymapProvider):
    """Mock keymap provider for testing custom keymaps."""

    def __init__(
        self,
        leader_commands: list[LeaderCommandDef] | None = None,
        action_keys: list[ActionKeyDef] | None = None,
    ):
        self._leader_commands = leader_commands or []
        self._action_keys = action_keys or []

    def get_leader_commands(self) -> list[LeaderCommandDef]:
        return self._leader_commands

    def get_action_keys(self) -> list[ActionKeyDef]:
        return self._action_keys


@pytest.fixture(autouse=True)
def reset_keymap_after_test():
    """Reset keymap after each test to avoid cross-test pollution."""
    yield
    reset_keymap()
