"""Unit tests for query deletion helpers."""

from __future__ import annotations

from sqlit.domains.query.editing import deletion


def test_delete_line_removes_line_and_clamps_cursor() -> None:
    text = "one\ntwo\nthree"
    result = deletion.delete_line(text, row=1, col=99)

    assert result.text == "one\nthree"
    assert result.row == 1
    assert result.col == len("two")


def test_delete_word_removes_word_and_trailing_space() -> None:
    text = "select  foo"
    result = deletion.delete_word(text, row=0, col=0)

    assert result.text == "foo"
    assert result.row == 0
    assert result.col == 0


def test_delete_word_back_removes_previous_word() -> None:
    text = "select foo"
    result = deletion.delete_word_back(text, row=0, col=len(text))

    assert result.text == "select "
    assert result.row == 0
    assert result.col == len("select ")


def test_delete_char_removes_newline() -> None:
    text = "ab\ncd"
    result = deletion.delete_char(text, row=0, col=2)

    assert result.text == "abcd"
    assert result.row == 0
    assert result.col == 2


def test_delete_all_clears_text() -> None:
    result = deletion.delete_all("anything", row=3, col=5)

    assert result.text == ""
    assert result.row == 0
    assert result.col == 0
