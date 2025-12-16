"""Tests for the keymap provider pattern."""

from __future__ import annotations

from sqlit.keymap import (
    ActionKeyDef,
    LeaderCommandDef,
    get_keymap,
    reset_keymap,
    set_keymap,
)
from sqlit.state_machine import get_leader_commands

from .conftest import MockKeymapProvider


class TestKeymapProvider:
    """Test the keymap provider pattern."""

    def test_default_keymap_has_expected_leader_commands(self):
        """Default keymap should have standard leader commands."""
        keymap = get_keymap()

        # Verify leader commands exist (don't check specific keys)
        assert keymap.leader("quit") is not None
        assert keymap.leader("show_help") is not None
        assert keymap.leader("toggle_explorer") is not None
        assert keymap.leader("change_theme") is not None

    def test_default_keymap_has_expected_action_keys(self):
        """Default keymap should have standard action keys."""
        keymap = get_keymap()

        # Verify action keys exist (don't check specific keys)
        assert keymap.action("new_connection") is not None
        assert keymap.action("focus_query") is not None
        assert keymap.action("focus_explorer") is not None

    def test_custom_keymap_can_be_set(self):
        """Custom keymap provider can be injected."""
        custom_keymap = MockKeymapProvider(
            leader_commands=[
                LeaderCommandDef("x", "quit", "Quit", "Actions"),
                LeaderCommandDef("?", "show_help", "Help", "Actions"),
            ],
            action_keys=[
                ActionKeyDef("a", "new_connection", "tree"),
            ],
        )

        set_keymap(custom_keymap)

        keymap = get_keymap()
        assert keymap.leader("quit") == "x"
        assert keymap.leader("show_help") == "?"
        assert keymap.action("new_connection") == "a"

    def test_leader_commands_reflect_custom_keymap(self):
        """get_leader_commands() should use the current keymap."""
        custom_keymap = MockKeymapProvider(
            leader_commands=[
                LeaderCommandDef("z", "quit", "Exit", "Actions"),
            ],
        )

        set_keymap(custom_keymap)

        leader_commands = get_leader_commands()
        assert len(leader_commands) == 1
        assert leader_commands[0].key == "z"
        assert leader_commands[0].action == "quit"

    def test_reset_keymap_restores_default(self):
        """reset_keymap() should restore the default keymap."""
        default_quit_key = get_keymap().leader("quit")

        custom_keymap = MockKeymapProvider(
            leader_commands=[
                LeaderCommandDef("x", "quit", "Quit", "Actions"),
            ],
        )
        set_keymap(custom_keymap)
        assert get_keymap().leader("quit") == "x"

        reset_keymap()
        assert get_keymap().leader("quit") == default_quit_key
