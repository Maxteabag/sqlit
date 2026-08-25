"""Saved-query library and query document lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlit.domains.query.app.document import QueryDocument
from sqlit.domains.query.store.saved_queries import (
    FileFingerprint,
    SavedQueryConflictError,
    SavedQueryEntry,
    SavedQueryNameError,
)
from sqlit.shared.ui.protocols import QueryMixinHost


class QueryDocumentsMixin:
    """Load, save, and protect user-managed SQL files."""

    _query_document: QueryDocument | None = None

    def _get_query_document(self: QueryMixinHost) -> QueryDocument:
        document = getattr(self, "_query_document", None)
        if document is None:
            document = QueryDocument()
            self._query_document = document
        return document

    def _document_is_dirty(self: QueryMixinHost) -> bool:
        return bool(self._get_query_document().is_dirty(self.query_input.text))

    def _query_document_label(self: QueryMixinHost) -> str:
        document = self._get_query_document()
        if document.relative_path is None:
            return "Query"
        name = document.name
        if len(name) > 42:
            name = f"…{name[-41:]}"
        marker = " ●" if document.is_dirty(self.query_input.text) else ""
        return f"Query — {name}{marker}"

    def _update_query_document_title(self: QueryMixinHost) -> None:
        updater = getattr(self, "_sync_active_pane_title", None)
        if callable(updater):
            updater()

    def _set_query_document(
        self: QueryMixinHost,
        *,
        connection_name: str | None,
        relative_path: str | None,
        saved_text: str,
        fingerprint: Any | None,
    ) -> None:
        self._query_document = QueryDocument(
            connection_name=connection_name,
            relative_path=relative_path,
            saved_text=saved_text,
            fingerprint=fingerprint,
        )
        self._update_query_document_title()

    def _load_saved_query_entry(self: QueryMixinHost, entry: SavedQueryEntry) -> None:
        connection_name = self.current_config.name if self.current_config else None
        self._apply_history_query(entry.query)
        self._set_query_document(
            connection_name=connection_name,
            relative_path=entry.relative_path,
            saved_text=entry.query,
            fingerprint=entry.fingerprint,
        )
        self.notify(f"Opened {entry.relative_path}")

    def _load_unsaved_query_text(self: QueryMixinHost, query: str) -> None:
        connection_name = self.current_config.name if self.current_config else None
        self._apply_history_query(query)
        self._set_query_document(
            connection_name=connection_name,
            relative_path=None,
            saved_text="",
            fingerprint=None,
        )

    def _reset_query_document(self: QueryMixinHost, *, clear_text: bool) -> None:
        if clear_text:
            self.query_input.text = ""
        connection_name = self.current_config.name if self.current_config else None
        self._set_query_document(
            connection_name=connection_name,
            relative_path=None,
            saved_text=self.query_input.text,
            fingerprint=None,
        )

    def _require_saved_query_connection(self: QueryMixinHost) -> str | None:
        config = self.current_config
        if config is None:
            self.notify("Connect to a saved connection first", severity="warning")
            return None
        saved_names = {connection.name for connection in getattr(self, "connections", [])}
        if config.name not in saved_names:
            self.notify("Save this connection before saving query files", severity="warning")
            return None
        return config.name

    def action_query_library(self: QueryMixinHost) -> None:
        connection_name = self._require_saved_query_connection()
        if connection_name is None:
            return
        from sqlit.domains.query.ui.screens import QueryLibraryScreen

        entries = self.services.saved_query_store.list_for_connection(connection_name)

        def on_selected(entry: SavedQueryEntry | None) -> None:
            if entry is None:
                return
            try:
                current_entry = self.services.saved_query_store.load(
                    connection_name, entry.relative_path
                )
            except (OSError, UnicodeError, SavedQueryNameError) as exc:
                self.notify(f"Could not open saved query: {exc}", severity="error")
                return
            self._request_query_document_transition(
                lambda: self._load_saved_query_entry(current_entry)
            )

        self.push_screen(QueryLibraryScreen(entries, connection_name), on_selected)

    def action_save_query(self: QueryMixinHost) -> None:
        connection_name = self._require_saved_query_connection()
        if connection_name is None:
            return
        if not self.query_input.text.strip():
            self.notify("There is no query to save", severity="warning")
            return
        document = self._get_query_document()
        if document.relative_path and document.connection_name == connection_name:
            self._save_existing_query_document(connection_name, document)
            return
        self._prompt_saved_query_name(connection_name)

    def action_save_query_as(self: QueryMixinHost) -> None:
        connection_name = self._require_saved_query_connection()
        if connection_name is None:
            return
        if not self.query_input.text.strip():
            self.notify("There is no query to save", severity="warning")
            return
        document = self._get_query_document()
        self._prompt_saved_query_name(
            connection_name,
            initial_name=document.relative_path or "",
            title="Save Query As",
        )

    def _save_existing_query_document(
        self: QueryMixinHost,
        connection_name: str,
        document: QueryDocument,
        *,
        after_save: Callable[[], None] | None = None,
    ) -> None:
        assert document.relative_path is not None
        try:
            entry = self.services.saved_query_store.save(
                connection_name,
                document.relative_path,
                self.query_input.text,
                expected=document.fingerprint,
            )
        except SavedQueryConflictError:
            self._resolve_external_query_change(
                connection_name,
                document,
                after_save=after_save,
            )
            return
        except (OSError, SavedQueryNameError) as exc:
            self.notify(f"Could not save query: {exc}", severity="error")
            return
        self._finish_query_save(connection_name, entry, after_save=after_save)

    def _prompt_saved_query_name(
        self: QueryMixinHost,
        connection_name: str,
        *,
        initial_name: str = "",
        title: str = "Save Query",
        after_save: Callable[[], None] | None = None,
    ) -> None:
        from sqlit.domains.query.ui.screens import SavedQueryNameScreen

        def on_name(name: str | None) -> None:
            if not name:
                return
            self._save_new_query_name(
                connection_name,
                name,
                after_save=after_save,
            )

        self.push_screen(
            SavedQueryNameScreen(initial_name=initial_name, title=title),
            on_name,
        )

    def _save_new_query_name(
        self: QueryMixinHost,
        connection_name: str,
        name: str,
        *,
        after_save: Callable[[], None] | None = None,
        overwrite: bool = False,
        expected: FileFingerprint | None = None,
    ) -> None:
        try:
            entry = self.services.saved_query_store.save(
                connection_name,
                name,
                self.query_input.text,
                expected=expected,
                overwrite=overwrite,
            )
        except FileExistsError as exc:
            from sqlit.shared.ui.screens.confirm import ConfirmScreen

            relative_path = str(exc)
            replacement_fingerprint = (
                self.services.saved_query_store.current_fingerprint(
                    connection_name, name
                )
            )

            def on_overwrite(confirmed: bool | None) -> None:
                if confirmed:
                    self._save_new_query_name(
                        connection_name,
                        name,
                        after_save=after_save,
                        overwrite=True,
                        expected=replacement_fingerprint,
                    )

            self.push_screen(
                ConfirmScreen(
                    f"Replace {relative_path}?",
                    yes_label="Replace",
                    no_label="Cancel",
                ),
                on_overwrite,
            )
            return
        except SavedQueryConflictError:
            self.notify(
                "The saved query changed while confirmation was open; review it again",
                severity="warning",
            )
            self._save_new_query_name(
                connection_name,
                name,
                after_save=after_save,
            )
            return
        except (OSError, SavedQueryNameError) as exc:
            self.notify(f"Could not save query: {exc}", severity="error")
            return
        self._finish_query_save(connection_name, entry, after_save=after_save)

    def _finish_query_save(
        self: QueryMixinHost,
        connection_name: str,
        entry: SavedQueryEntry,
        *,
        after_save: Callable[[], None] | None,
    ) -> None:
        self._set_query_document(
            connection_name=connection_name,
            relative_path=entry.relative_path,
            saved_text=entry.query,
            fingerprint=entry.fingerprint,
        )
        self.notify(f"Saved {entry.relative_path}")
        refresh_tree = getattr(self, "_refresh_connection_tree", None)
        if callable(refresh_tree):
            refresh_tree()
        if after_save is not None:
            after_save()

    def _resolve_external_query_change(
        self: QueryMixinHost,
        connection_name: str,
        document: QueryDocument,
        *,
        after_save: Callable[[], None] | None,
    ) -> None:
        from sqlit.domains.query.ui.screens import ExternalQueryChangeScreen

        assert document.relative_path is not None
        conflict_fingerprint = self.services.saved_query_store.current_fingerprint(
            connection_name, document.relative_path
        )

        def on_choice(choice: str | None) -> None:
            if choice in {None, "cancel"}:
                return
            if choice == "reload":
                try:
                    entry = self.services.saved_query_store.load(connection_name, document.relative_path)
                except (OSError, UnicodeError, SavedQueryNameError) as exc:
                    self.notify(f"Could not reload query: {exc}", severity="error")
                    return
                self._load_saved_query_entry(entry)
                if after_save is not None:
                    after_save()
                return
            if choice == "overwrite":
                self._save_new_query_name(
                    connection_name,
                    document.relative_path,
                    after_save=after_save,
                    overwrite=True,
                    expected=conflict_fingerprint,
                )
                return
            if choice == "save_as":
                self._prompt_saved_query_name(
                    connection_name,
                    initial_name=document.relative_path,
                    title="Save Query As",
                    after_save=after_save,
                )

        self.push_screen(ExternalQueryChangeScreen(document.name), on_choice)

    def _request_query_document_transition(self: QueryMixinHost, continuation: Callable[[], None]) -> bool:
        document = self._get_query_document()
        if (
            document.relative_path is None
            or not document.is_dirty(self.query_input.text)
        ):
            continuation()
            return False

        from sqlit.domains.query.ui.screens import UnsavedQueryChangesScreen

        def on_choice(choice: str | None) -> None:
            if choice in {None, "cancel"}:
                return
            if choice == "discard":
                self._set_query_document(
                    connection_name=(
                        self.current_config.name if self.current_config else None
                    ),
                    relative_path=None,
                    saved_text=self.query_input.text,
                    fingerprint=None,
                )
                continuation()
                return
            if choice == "save":
                connection_name = self._require_saved_query_connection()
                if connection_name is None:
                    return
                if document.relative_path and document.connection_name == connection_name:
                    self._save_existing_query_document(
                        connection_name,
                        document,
                        after_save=continuation,
                    )
                else:
                    self._prompt_saved_query_name(
                        connection_name,
                        after_save=continuation,
                    )

        self.push_screen(UnsavedQueryChangesScreen(document.name), on_choice)
        return True
