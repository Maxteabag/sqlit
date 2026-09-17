"""Query document dirty-state semantics."""

from sqlit.domains.query.app.document import QueryDocument


def test_untitled_document_is_clean_when_empty() -> None:
    assert QueryDocument().is_dirty("") is False


def test_editing_marks_document_dirty() -> None:
    document = QueryDocument(relative_path="report.sql", saved_text="SELECT 1")
    assert document.is_dirty("SELECT 2") is True


def test_undoing_to_saved_text_clears_dirty_state() -> None:
    document = QueryDocument(relative_path="report.sql", saved_text="SELECT 1")
    assert document.is_dirty("SELECT 2") is True
    assert document.is_dirty("SELECT 1") is False
