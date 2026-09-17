"""Regression coverage for promoting leader commands to direct keys (#321)."""

from __future__ import annotations

import pytest

from sqlit.core.key_router import resolve_action
from sqlit.core.keymap import get_keymap, set_keymap
from sqlit.core.vim import VimMode
from sqlit.domains.shell.app.keymap_manager import KeymapManager
from sqlit.domains.shell.state import UIStateMachine

from .test_keymap_manager import MockSettingsStore
from .test_state_machine import make_context


def load_bindings(actions, *, leader=None):
    manager = KeymapManager(settings_store=MockSettingsStore())
    provider = manager._build_provider_from_payload(
        {"keymap": {"action_keys": actions, "leader_commands": leader or {}}}, "test"
    )
    set_keymap(provider)
    return provider


def route(key="ctrl+g", **context):
    ctx = make_context(**context)
    machine = UIStateMachine()
    return resolve_action(key, ctx, is_allowed=lambda action: machine.check_action(ctx, action))


@pytest.mark.parametrize("action", ["edit_query_in_editor", "format_query", "telescope", "change_theme"])
def test_direct_command_preserves_leader_binding(action):
    original = get_keymap().leader(action)
    load_bindings({"query_normal": {action: "ctrl+g"}})
    assert route(focus="query") == action
    assert get_keymap().leader(action) == original
    assert route(focus="results") is None
    assert route(focus="query", vim_mode=VimMode.INSERT) is None
    assert route(original, focus="query", leader_pending=True) == f"leader_{action}"


def test_aliases_and_independent_leader_unbinding():
    provider = load_bindings(
        {"query_normal": {"telescope": ["ctrl+g", "ctrl+t"]}},
        leader={"leader": {"telescope": None}},
    )
    assert provider.keys_for_action("telescope") == ["ctrl+g", "ctrl+t"]
    assert provider.leader("telescope") is None
    assert route(focus="query") == "telescope"
    assert route("ctrl+t", focus="query") == "telescope"


@pytest.mark.parametrize("value", [None, "", []])
def test_unbinding_direct_command_keeps_leader(value):
    load_bindings({"query_normal": {"telescope": value}})
    assert route(focus="query") is None
    assert get_keymap().leader("telescope") == "space"


@pytest.mark.parametrize(
    ("action", "context", "expected"),
    [
        ("format_query", {"focus": "results"}, None),
        ("format_query", {"focus": "query"}, "format_query"),
        ("disconnect", {"has_connection": False}, None),
        ("disconnect", {"has_connection": True}, "disconnect"),
        ("cancel_operation", {"query_executing": False}, None),
        ("cancel_operation", {"query_executing": True}, "cancel_operation"),
        ("telescope", {"modal_open": True}, None),
        ("show_help", {"focus": "query", "vim_mode": VimMode.INSERT}, None),
    ],
)
def test_direct_command_respects_guards_and_state_restrictions(action, context, expected):
    load_bindings({"global": {action: "ctrl+g"}})
    assert route(**context) == expected


@pytest.mark.parametrize(
    "actions",
    [
        {"query_normal": {"telescope": "enter"}},
        {"query_normal": {"telescope": "ctrl+g", "change_theme": "ctrl+g"}},
        {"query_normal": {"telescope": "q"}},  # shadows navigation focus_query
    ],
)
def test_promoted_command_uses_existing_conflict_detection(actions):
    with pytest.raises(ValueError, match=r"conflict|multiple actions|shadow"):
        load_bindings(actions)


def test_unbinding_conflicting_default_allows_promotion():
    load_bindings({"query_normal": {"execute_query": None, "telescope": "enter"}})
    assert route("enter", focus="query") == "telescope"


@pytest.mark.parametrize("scope", ["made_up_state", "connection_editor", "error_dialog"])
def test_promotions_reject_unknown_or_screen_local_scopes(scope):
    with pytest.raises(ValueError, match="Unknown action"):
        load_bindings({scope: {"telescope": "ctrl+g"}})


@pytest.mark.parametrize("action", ["word", "line", "not_an_action"])
def test_submenu_motions_and_unknown_actions_are_not_promoted(action):
    with pytest.raises(ValueError, match="Unknown action"):
        load_bindings({"query_normal": {action: "ctrl+g"}})


@pytest.mark.parametrize("action", ["edit_query_in_editor", "telescope", "change_theme"])
@pytest.mark.parametrize("key", ["ctrl+g", "ctrl+a", "ctrl+c", "ctrl+v"])
async def test_direct_key_and_leader_key_dispatch_in_headless_app(tmp_path, monkeypatch, action, key):
    import json

    from sqlit.domains.shell.app import keymap_manager

    from .test_leader import _make_app

    path = tmp_path / "keymap.json"
    path.write_text(json.dumps({"keymap": {"action_keys": {"query_normal": {action: key}}}}))
    monkeypatch.setattr(keymap_manager, "DEFAULT_KEYMAP_FILE", path)
    app = _make_app()
    calls = []
    monkeypatch.setattr(app, f"action_{action}", lambda: calls.append(action))
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        await pilot.pause()
        await pilot.press(key)
        assert calls == [action]
        await pilot.press("space", get_keymap().leader(action))
        assert calls == [action, action]


@pytest.mark.parametrize("override_order", ["default", "insert_first", "autocomplete_first"])
async def test_autocomplete_binding_takes_precedence_over_insert_command(tmp_path, monkeypatch, override_order):
    import json

    from sqlit.domains.shell.app import keymap_manager

    from .test_leader import _make_app

    path = tmp_path / "keymap.json"
    actions = {"query_insert": {"telescope": "ctrl+j"}}
    if override_order != "default":
        actions["autocomplete"] = {"autocomplete_next": "ctrl+j"}
        if override_order == "autocomplete_first":
            actions = dict(reversed(list(actions.items())))
    path.write_text(json.dumps({"keymap": {"action_keys": actions}}))
    monkeypatch.setattr(keymap_manager, "DEFAULT_KEYMAP_FILE", path)
    app = _make_app()
    calls = []
    monkeypatch.setattr(app, "action_telescope", lambda: calls.append("telescope"))
    monkeypatch.setattr(app, "action_autocomplete_next", lambda: calls.append("autocomplete_next"))
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        await pilot.pause()
        app.action_enter_insert_mode()
        await pilot.pause()
        app._autocomplete_visible = True
        assert app._get_input_context().autocomplete_visible
        assert app._get_input_context().vim_mode == VimMode.INSERT
        assert app.check_action("autocomplete_next", ()) is True
        await pilot.press("ctrl+j")
        assert calls == ["autocomplete_next"]
        app._autocomplete_visible = False
        await pilot.press("ctrl+j")
        assert calls == ["autocomplete_next", "telescope"]
