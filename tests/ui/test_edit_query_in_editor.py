"""End-to-end tests for the 'Edit query in editor' leader command."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from sqlit.domains.shell.app.main import SSMSTUI


@contextmanager
def _noop_suspend(*_args, **_kwargs):
    yield

from .mocks import (
    MockConnectionStore,
    MockHistoryStore,
    MockSettingsStore,
    build_test_services,
    create_test_connection,
)


def _make_app(settings: dict | None = None) -> SSMSTUI:
    conn = create_test_connection("test-conn", "sqlite")
    services = build_test_services(
        connection_store=MockConnectionStore([conn]),
        settings_store=MockSettingsStore(settings or {"theme": "tokyo-night"}),
        history_store=MockHistoryStore(),
    )
    return SSMSTUI(services=services)


def _fake_editor_writes(new_text: str):
    """Return a subprocess.run replacement that overwrites the temp file's
    contents with `new_text`, simulating an editor session."""

    def _run(argv, *args, **kwargs):
        path = Path(argv[-1])
        path.write_text(new_text, encoding="utf-8")

        class _Result:
            returncode = 0

        return _Result()

    return _run


class TestEditQueryInEditor:
    @pytest.mark.asyncio
    async def test_invokes_preferred_editor_and_updates_buffer(self):
        """With a saved preference + installed editor, run subprocess and
        load the edited content back into the query buffer."""
        app = _make_app(settings={"theme": "tokyo-night", "preferred_editor": "nvim"})

        async with app.run_test(size=(120, 40)) as pilot:
            app.query_input.text = "SELECT 1"
            await pilot.pause()

            with patch(
                "sqlit.domains.query.app.editor.shutil.which",
                side_effect=lambda cmd: "/usr/bin/nvim" if cmd == "nvim" else None,
            ), patch(
                "subprocess.run",
                side_effect=_fake_editor_writes("SELECT 2 FROM users"),
            ), patch.object(app, "suspend", _noop_suspend):
                app.action_edit_query_in_editor()
                await pilot.pause()

            assert app.query_input.text == "SELECT 2 FROM users"

    @pytest.mark.asyncio
    async def test_picker_opens_when_no_preference_but_editor_detected(self):
        """Empty settings + no env editor + at least one installed editor → picker pops up."""
        from sqlit.domains.query.ui.screens import EditorPickerScreen

        app = _make_app(settings={"theme": "tokyo-night"})

        async with app.run_test(size=(120, 40)) as pilot:
            app.query_input.text = "SELECT 1"
            await pilot.pause()

            with patch(
                "sqlit.domains.query.app.editor.shutil.which",
                side_effect=lambda cmd: "/usr/bin/nvim" if cmd == "nvim" else None,
            ), patch.dict("os.environ", {}, clear=False) as env:
                env.pop("VISUAL", None)
                env.pop("EDITOR", None)
                app.action_edit_query_in_editor()
                await pilot.pause()

            assert any(
                isinstance(screen, EditorPickerScreen)
                for screen in app.screen_stack
            )

    @pytest.mark.asyncio
    async def test_no_picker_when_no_editor_detected(self):
        """Nothing installed at all → notify with install hint, no picker."""
        from sqlit.domains.query.ui.screens import EditorPickerScreen

        app = _make_app(settings={"theme": "tokyo-night"})
        notifications: list[str] = []
        original_notify = app.notify
        app.notify = lambda msg, **kw: (notifications.append(msg), original_notify(msg, **kw))[1]  # type: ignore[assignment]

        async with app.run_test(size=(120, 40)) as pilot:
            app.query_input.text = "SELECT 1"
            await pilot.pause()

            with patch(
                "sqlit.domains.query.app.editor.shutil.which", return_value=None
            ), patch.dict("os.environ", {}, clear=False) as env:
                env.pop("VISUAL", None)
                env.pop("EDITOR", None)
                app.action_edit_query_in_editor()
                await pilot.pause()

            assert not any(
                isinstance(screen, EditorPickerScreen) for screen in app.screen_stack
            )
            assert any("No terminal editor detected" in n for n in notifications)

    @pytest.mark.asyncio
    async def test_no_change_when_buffer_text_unchanged(self):
        """If the editor closes without modifying the file, nothing happens
        (history isn't touched, buffer is untouched)."""
        app = _make_app(settings={"theme": "tokyo-night", "preferred_editor": "nvim"})

        async with app.run_test(size=(120, 40)) as pilot:
            app.query_input.text = "SELECT same"
            await pilot.pause()

            with patch(
                "sqlit.domains.query.app.editor.shutil.which",
                side_effect=lambda cmd: "/usr/bin/nvim" if cmd == "nvim" else None,
            ), patch(
                "subprocess.run", side_effect=_fake_editor_writes("SELECT same")
            ), patch.object(app, "suspend", _noop_suspend):
                app.action_edit_query_in_editor()
                await pilot.pause()

            assert app.query_input.text == "SELECT same"
            # MockHistoryStore tracks save_query calls via its entries dict.
            assert app.services.history_store.entries == {}
