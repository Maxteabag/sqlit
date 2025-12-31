"""Unit tests for vim operators."""

from __future__ import annotations

import pytest

from sqlit.domains.query.editing.types import (
    MotionType,
    Position,
    Range,
)
from sqlit.domains.query.editing.operators import (
    operator_delete,
    operator_yank,
    operator_change,
    OPERATORS,
)


class TestOperatorDelete:
    """Tests for the delete operator."""

    def test_delete_charwise_single_line(self) -> None:
        text = "hello world"
        range_obj = Range(Position(0, 0), Position(0, 5), MotionType.CHARWISE, inclusive=False)
        result = operator_delete(text, range_obj)
        assert result.text == " world"
        assert result.row == 0
        assert result.col == 0
        assert result.yanked == "hello"

    def test_delete_charwise_inclusive(self) -> None:
        text = "hello world"
        range_obj = Range(Position(0, 0), Position(0, 4), MotionType.CHARWISE, inclusive=True)
        result = operator_delete(text, range_obj)
        assert result.text == " world"
        assert result.yanked == "hello"

    def test_delete_charwise_middle(self) -> None:
        text = "hello world"
        range_obj = Range(Position(0, 3), Position(0, 7), MotionType.CHARWISE, inclusive=False)
        result = operator_delete(text, range_obj)
        assert result.text == "helorld"
        assert result.yanked == "lo w"

    def test_delete_charwise_multiline(self) -> None:
        text = "line1\nline2\nline3"
        range_obj = Range(Position(0, 3), Position(1, 3), MotionType.CHARWISE, inclusive=False)
        result = operator_delete(text, range_obj)
        assert result.text == "line2\nline3"
        assert "e1\nlin" in result.yanked

    def test_delete_linewise_single_line(self) -> None:
        text = "line1\nline2\nline3"
        range_obj = Range(Position(1, 0), Position(1, 5), MotionType.LINEWISE)
        result = operator_delete(text, range_obj)
        assert result.text == "line1\nline3"
        assert result.row == 1
        assert result.col == 0
        assert result.yanked == "line2"

    def test_delete_linewise_multiple_lines(self) -> None:
        text = "line1\nline2\nline3\nline4"
        range_obj = Range(Position(1, 0), Position(2, 5), MotionType.LINEWISE)
        result = operator_delete(text, range_obj)
        assert result.text == "line1\nline4"
        assert result.yanked == "line2\nline3"

    def test_delete_linewise_all_lines(self) -> None:
        text = "line1\nline2"
        range_obj = Range(Position(0, 0), Position(1, 5), MotionType.LINEWISE)
        result = operator_delete(text, range_obj)
        assert result.text == ""
        assert result.row == 0
        assert result.col == 0

    def test_delete_empty_text(self) -> None:
        text = ""
        range_obj = Range(Position(0, 0), Position(0, 0), MotionType.CHARWISE)
        result = operator_delete(text, range_obj)
        assert result.text == ""
        assert result.yanked == ""

    def test_delete_reversed_range(self) -> None:
        # Range with end before start should be ordered
        text = "hello world"
        range_obj = Range(Position(0, 5), Position(0, 0), MotionType.CHARWISE, inclusive=False)
        result = operator_delete(text, range_obj)
        assert result.text == " world"
        assert result.yanked == "hello"


class TestOperatorYank:
    """Tests for the yank operator."""

    def test_yank_charwise(self) -> None:
        text = "hello world"
        range_obj = Range(Position(0, 0), Position(0, 5), MotionType.CHARWISE, inclusive=False)
        result = operator_yank(text, range_obj)
        assert result.text == text  # Text unchanged
        assert result.yanked == "hello"
        assert result.row == 0
        assert result.col == 0

    def test_yank_charwise_inclusive(self) -> None:
        text = "hello world"
        range_obj = Range(Position(0, 0), Position(0, 4), MotionType.CHARWISE, inclusive=True)
        result = operator_yank(text, range_obj)
        assert result.yanked == "hello"

    def test_yank_linewise(self) -> None:
        text = "line1\nline2\nline3"
        range_obj = Range(Position(1, 0), Position(1, 5), MotionType.LINEWISE)
        result = operator_yank(text, range_obj)
        assert result.text == text  # Text unchanged
        assert result.yanked == "line2"

    def test_yank_multiline(self) -> None:
        text = "line1\nline2\nline3"
        range_obj = Range(Position(0, 3), Position(1, 3), MotionType.CHARWISE, inclusive=False)
        result = operator_yank(text, range_obj)
        assert result.text == text
        assert "e1\nlin" in result.yanked


class TestOperatorChange:
    """Tests for the change operator."""

    def test_change_deletes_and_sets_insert_flag(self) -> None:
        text = "hello world"
        range_obj = Range(Position(0, 0), Position(0, 5), MotionType.CHARWISE, inclusive=False)
        result = operator_change(text, range_obj)
        assert result.text == " world"
        assert result.yanked == "hello"
        assert result.enter_insert is True

    def test_change_linewise(self) -> None:
        text = "line1\nline2\nline3"
        range_obj = Range(Position(1, 0), Position(1, 5), MotionType.LINEWISE)
        result = operator_change(text, range_obj)
        assert result.text == "line1\nline3"
        assert result.enter_insert is True


class TestOperatorRegistry:
    """Tests for OPERATORS registry."""

    def test_all_operators_registered(self) -> None:
        assert set(OPERATORS.keys()) == {"d", "y", "c"}

    def test_operators_are_callable(self) -> None:
        text = "test"
        range_obj = Range(Position(0, 0), Position(0, 2), MotionType.CHARWISE)

        for key, op in OPERATORS.items():
            result = op(text, range_obj)
            assert hasattr(result, "text")
            assert hasattr(result, "yanked")
