"""Unit tests for vim motion engine."""

from __future__ import annotations

from sqlit.domains.query.editing.motions.basic import (
    motion_down,
    motion_left,
    motion_right,
    motion_up,
)
from sqlit.domains.query.editing.motions.brackets import motion_matching_bracket
from sqlit.domains.query.editing.motions.lines import (
    motion_last_line,
    motion_line_end,
    motion_line_start,
)
from sqlit.domains.query.editing.motions.registry import CHAR_MOTIONS, MOTIONS
from sqlit.domains.query.editing.motions.search import (
    motion_find_char,
    motion_find_char_back,
    motion_till_char,
    motion_till_char_back,
)
from sqlit.domains.query.editing.motions.words import (
    motion_WORD,
    motion_WORD_back,
    motion_WORD_end,
    motion_word,
    motion_word_back,
    motion_word_end,
)
from sqlit.domains.query.editing.types import (
    MotionType,
    Position,
    Range,
)


class TestBasicMotions:
    """Tests for h, j, k, l motions."""

    def test_motion_left(self) -> None:
        result = motion_left("hello", row=0, col=3)
        assert result.position == Position(0, 2)
        assert result.range is not None
        assert result.range.start == Position(0, 2)
        assert result.range.end == Position(0, 3)

    def test_motion_left_at_start(self) -> None:
        result = motion_left("hello", row=0, col=0)
        assert result.position == Position(0, 0)

    def test_motion_right(self) -> None:
        result = motion_right("hello", row=0, col=2)
        assert result.position == Position(0, 3)
        assert result.range is not None
        assert result.range.start == Position(0, 2)
        assert result.range.end == Position(0, 3)

    def test_motion_right_at_end(self) -> None:
        result = motion_right("hello", row=0, col=5)
        assert result.position == Position(0, 5)

    def test_motion_down(self) -> None:
        result = motion_down("line1\nline2\nline3", row=0, col=2)
        assert result.position == Position(1, 2)
        assert result.range is not None
        assert result.range.motion_type == MotionType.LINEWISE

    def test_motion_down_at_last_line(self) -> None:
        result = motion_down("line1\nline2", row=1, col=0)
        assert result.position == Position(1, 0)

    def test_motion_up(self) -> None:
        result = motion_up("line1\nline2\nline3", row=2, col=2)
        assert result.position == Position(1, 2)
        assert result.range is not None
        assert result.range.motion_type == MotionType.LINEWISE

    def test_motion_up_at_first_line(self) -> None:
        result = motion_up("line1\nline2", row=0, col=0)
        assert result.position == Position(0, 0)


class TestWordMotions:
    """Tests for w, W, b, B, e, E motions."""

    def test_motion_word(self) -> None:
        result = motion_word("hello world", row=0, col=0)
        assert result.position == Position(0, 6)

    def test_motion_word_on_punctuation(self) -> None:
        result = motion_word("foo.bar", row=0, col=0)
        # Should move to '.' then to 'bar'
        assert result.position.col > 0

    def test_motion_WORD(self) -> None:
        result = motion_WORD("foo.bar baz", row=0, col=0)
        assert result.position == Position(0, 8)  # "baz" starts at 8

    def test_motion_word_back(self) -> None:
        result = motion_word_back("hello world", row=0, col=8)
        assert result.position == Position(0, 6)

    def test_motion_word_back_at_start(self) -> None:
        result = motion_word_back("hello", row=0, col=0)
        assert result.position == Position(0, 0)

    def test_motion_WORD_back(self) -> None:
        result = motion_WORD_back("foo.bar baz", row=0, col=10)
        assert result.position == Position(0, 8)

    def test_motion_word_end(self) -> None:
        result = motion_word_end("hello world", row=0, col=0)
        assert result.position == Position(0, 4)  # 'o' of 'hello'

    def test_motion_word_end_inclusive(self) -> None:
        result = motion_word_end("hello world", row=0, col=0)
        assert result.range is not None
        assert result.range.inclusive is True

    def test_motion_WORD_end(self) -> None:
        result = motion_WORD_end("foo.bar baz", row=0, col=0)
        assert result.position == Position(0, 6)  # 'r' of 'foo.bar'


class TestLineMotions:
    """Tests for 0, $, G motions."""

    def test_motion_line_start(self) -> None:
        result = motion_line_start("  hello", row=0, col=5)
        assert result.position == Position(0, 0)

    def test_motion_line_end(self) -> None:
        result = motion_line_end("hello", row=0, col=0)
        assert result.position == Position(0, 5)
        assert result.range is not None
        assert result.range.inclusive is True

    def test_motion_last_line(self) -> None:
        result = motion_last_line("line1\nline2\nline3", row=0, col=0)
        assert result.position == Position(2, 0)
        assert result.range is not None
        assert result.range.motion_type == MotionType.LINEWISE


class TestCharSearchMotions:
    """Tests for f, F, t, T motions."""

    def test_motion_find_char(self) -> None:
        result = motion_find_char("hello;world", row=0, col=0, char=";")
        assert result.position == Position(0, 5)

    def test_motion_find_char_not_found(self) -> None:
        result = motion_find_char("hello", row=0, col=0, char="x")
        assert result.position == Position(0, 0)  # Stay in place

    def test_motion_find_char_no_char(self) -> None:
        result = motion_find_char("hello", row=0, col=0, char=None)
        assert result.position == Position(0, 0)

    def test_motion_find_char_back(self) -> None:
        result = motion_find_char_back("hello;world", row=0, col=10, char=";")
        assert result.position == Position(0, 5)

    def test_motion_till_char(self) -> None:
        result = motion_till_char("hello;world", row=0, col=0, char=";")
        assert result.position == Position(0, 4)  # One before ';'

    def test_motion_till_char_back(self) -> None:
        result = motion_till_char_back("hello;world", row=0, col=10, char=";")
        assert result.position == Position(0, 6)  # One after ';'


class TestBracketMatching:
    """Tests for % motion."""

    def test_motion_matching_bracket_forward(self) -> None:
        result = motion_matching_bracket("(hello)", row=0, col=0)
        assert result.position == Position(0, 6)

    def test_motion_matching_bracket_backward(self) -> None:
        result = motion_matching_bracket("(hello)", row=0, col=6)
        assert result.position == Position(0, 0)

    def test_motion_matching_bracket_nested(self) -> None:
        result = motion_matching_bracket("((inner))", row=0, col=0)
        assert result.position == Position(0, 8)

    def test_motion_matching_bracket_curly(self) -> None:
        result = motion_matching_bracket("{foo}", row=0, col=0)
        assert result.position == Position(0, 4)

    def test_motion_matching_bracket_square(self) -> None:
        result = motion_matching_bracket("[foo]", row=0, col=0)
        assert result.position == Position(0, 4)

    def test_motion_matching_bracket_multiline(self) -> None:
        result = motion_matching_bracket("(\n  inner\n)", row=0, col=0)
        assert result.position == Position(2, 0)

    def test_motion_matching_bracket_not_on_bracket(self) -> None:
        # Should search forward for a bracket
        result = motion_matching_bracket("x(y)", row=0, col=0)
        assert result.position == Position(0, 3)  # Matches ')'


class TestMotionRegistry:
    """Tests for the MOTIONS registry."""

    def test_all_motions_registered(self) -> None:
        expected = {
            "h", "j", "k", "l",
            "w", "W", "b", "B", "e", "E",
            "0", "$", "G", "gg", "ge", "gE", "_",
            "f", "F", "t", "T",
            "%",
        }
        assert set(MOTIONS.keys()) == expected

    def test_char_motions_identified(self) -> None:
        assert CHAR_MOTIONS == {"f", "F", "t", "T"}


class TestGMotions:
    """Tests for g prefix motions (gg, ge, gE)."""

    def test_gg_goes_to_first_line(self) -> None:
        """gg should go to first line."""
        text = "line1\nline2\nline3"
        result = MOTIONS["gg"](text, 2, 3, None)
        assert result.position.row == 0
        assert result.position.col == 0

    def test_gg_on_first_line_stays(self) -> None:
        """gg on first line should stay at first line."""
        text = "line1\nline2\nline3"
        result = MOTIONS["gg"](text, 0, 5, None)
        assert result.position.row == 0
        assert result.position.col == 0

    def test_ge_goes_to_end_of_previous_word(self) -> None:
        """ge should go to end of previous word."""
        text = "hello world"
        result = MOTIONS["ge"](text, 0, 7, None)  # Cursor on 'o' in 'world'
        assert result.position.row == 0
        assert result.position.col == 4  # End of 'hello'

    def test_ge_from_start_of_word(self) -> None:
        """ge from start of word should go to end of previous word."""
        text = "hello world"
        result = MOTIONS["ge"](text, 0, 6, None)  # Cursor at start of 'world'
        assert result.position.row == 0
        assert result.position.col == 4  # End of 'hello'

    def test_gE_goes_to_end_of_previous_WORD(self) -> None:
        """gE should go to end of previous WORD."""
        text = "hello-world foo"
        result = MOTIONS["gE"](text, 0, 13, None)  # Cursor in 'foo'
        assert result.position.row == 0
        assert result.position.col == 10  # End of 'hello-world'


class TestRangeHelpers:
    """Tests for Range helper methods."""

    def test_range_ordered(self) -> None:
        r = Range(Position(0, 5), Position(0, 2), MotionType.CHARWISE)
        ordered = r.ordered()
        assert ordered.start == Position(0, 2)
        assert ordered.end == Position(0, 5)

    def test_range_already_ordered(self) -> None:
        r = Range(Position(0, 2), Position(0, 5), MotionType.CHARWISE)
        ordered = r.ordered()
        assert ordered.start == Position(0, 2)
        assert ordered.end == Position(0, 5)


class TestPositionComparison:
    """Tests for Position comparison."""

    def test_position_lt_same_row(self) -> None:
        assert Position(0, 2) < Position(0, 5)
        assert not Position(0, 5) < Position(0, 2)

    def test_position_lt_different_row(self) -> None:
        assert Position(0, 5) < Position(1, 0)
        assert not Position(1, 0) < Position(0, 5)

    def test_position_le(self) -> None:
        assert Position(0, 2) <= Position(0, 2)
        assert Position(0, 2) <= Position(0, 5)
        assert not Position(0, 5) <= Position(0, 2)
