"""Tests for SQL comment toggle functionality."""

import pytest

from sqlit.domains.query.editing.comments import toggle_comment_lines


class TestToggleCommentLines:
    """Tests for toggle_comment_lines function."""

    def test_comment_single_line(self):
        """Test commenting a single line."""
        text = "SELECT * FROM users"
        new_text, col = toggle_comment_lines(text, 0, 0)
        assert new_text == "-- SELECT * FROM users"
        assert col == 3  # After "-- "

    def test_uncomment_single_line(self):
        """Test uncommenting a single line."""
        text = "-- SELECT * FROM users"
        new_text, col = toggle_comment_lines(text, 0, 0)
        assert new_text == "SELECT * FROM users"
        assert col == 0

    def test_comment_preserves_indentation(self):
        """Test that commenting preserves leading whitespace."""
        text = "    SELECT * FROM users"
        new_text, col = toggle_comment_lines(text, 0, 0)
        assert new_text == "    -- SELECT * FROM users"
        assert col == 7  # 4 spaces + "-- "

    def test_uncomment_preserves_indentation(self):
        """Test that uncommenting preserves leading whitespace."""
        text = "    -- SELECT * FROM users"
        new_text, col = toggle_comment_lines(text, 0, 0)
        assert new_text == "    SELECT * FROM users"
        assert col == 4  # Back to first non-whitespace

    def test_comment_multiple_lines(self):
        """Test commenting multiple lines."""
        text = "SELECT *\nFROM users\nWHERE id = 1"
        new_text, col = toggle_comment_lines(text, 0, 2)
        expected = "-- SELECT *\n-- FROM users\n-- WHERE id = 1"
        assert new_text == expected
        assert col == 3

    def test_uncomment_multiple_lines(self):
        """Test uncommenting multiple lines."""
        text = "-- SELECT *\n-- FROM users\n-- WHERE id = 1"
        new_text, col = toggle_comment_lines(text, 0, 2)
        expected = "SELECT *\nFROM users\nWHERE id = 1"
        assert new_text == expected
        assert col == 0

    def test_toggle_based_on_first_non_empty_line(self):
        """Test that toggle decision is based on first non-empty line."""
        text = "\nSELECT *\nFROM users"
        new_text, col = toggle_comment_lines(text, 0, 2)
        # First non-empty line (SELECT *) is not commented, so we comment all
        expected = "-- \n-- SELECT *\n-- FROM users"
        assert new_text == expected

    def test_mixed_commented_lines_comments_all(self):
        """Test that if first non-empty is uncommented, all get commented."""
        text = "SELECT *\n-- FROM users\nWHERE id = 1"
        new_text, col = toggle_comment_lines(text, 0, 2)
        expected = "-- SELECT *\n-- -- FROM users\n-- WHERE id = 1"
        assert new_text == expected

    def test_mixed_commented_lines_uncomments_all(self):
        """Test that if first non-empty is commented, all get uncommented."""
        text = "-- SELECT *\nFROM users\n-- WHERE id = 1"
        new_text, col = toggle_comment_lines(text, 0, 2)
        expected = "SELECT *\nFROM users\nWHERE id = 1"
        assert new_text == expected

    def test_empty_line_gets_comment_prefix(self):
        """Test that empty lines get comment prefix."""
        text = ""
        new_text, col = toggle_comment_lines(text, 0, 0)
        assert new_text == "-- "
        assert col == 3

    def test_whitespace_only_line(self):
        """Test commenting a whitespace-only line."""
        text = "    "
        new_text, col = toggle_comment_lines(text, 0, 0)
        assert new_text == "--     "
        assert col == 3

    def test_uncomment_without_space(self):
        """Test uncommenting --comment (without space after --)."""
        text = "--SELECT * FROM users"
        new_text, col = toggle_comment_lines(text, 0, 0)
        assert new_text == "SELECT * FROM users"
        assert col == 0

    def test_partial_range(self):
        """Test commenting only a subset of lines."""
        text = "SELECT *\nFROM users\nWHERE id = 1\nORDER BY name"
        new_text, col = toggle_comment_lines(text, 1, 2)
        expected = "SELECT *\n-- FROM users\n-- WHERE id = 1\nORDER BY name"
        assert new_text == expected

    def test_row_bounds_clamped(self):
        """Test that out-of-bounds rows are clamped."""
        text = "SELECT *\nFROM users"
        new_text, col = toggle_comment_lines(text, 0, 100)
        expected = "-- SELECT *\n-- FROM users"
        assert new_text == expected

    def test_negative_row_clamped(self):
        """Test that negative rows are clamped to 0."""
        text = "SELECT *\nFROM users"
        new_text, col = toggle_comment_lines(text, -5, 0)
        expected = "-- SELECT *"
        assert new_text == "-- SELECT *\nFROM users"

    def test_swapped_rows(self):
        """Test that start_row > end_row are swapped."""
        text = "SELECT *\nFROM users\nWHERE id = 1"
        new_text, col = toggle_comment_lines(text, 2, 0)
        expected = "-- SELECT *\n-- FROM users\n-- WHERE id = 1"
        assert new_text == expected

    def test_tabs_preserved(self):
        """Test that tab indentation is preserved."""
        text = "\tSELECT * FROM users"
        new_text, col = toggle_comment_lines(text, 0, 0)
        assert new_text == "\t-- SELECT * FROM users"
        assert col == 4  # 1 tab + "-- "

    @pytest.mark.parametrize(
        "text, start_row, end_row, expected_text, expected_col",
        [
            # Toggle on: simple multi-line
            (
                "SELECT *\nFROM users",
                0,
                1,
                "-- SELECT *\n-- FROM users",
                3,
            ),
            # Toggle off: simple multi-line
            (
                "-- SELECT *\n-- FROM users",
                0,
                1,
                "SELECT *\nFROM users",
                0,
            ),
            # Toggle on: mixed content (first line uncommented -> comment all)
            (
                "SELECT *\n-- FROM users",
                0,
                1,
                "-- SELECT *\n-- -- FROM users",
                3,
            ),
            # Toggle off: mixed content (first line commented -> uncomment all)
            (
                "-- SELECT *\nFROM users",
                0,
                1,
                "SELECT *\nFROM users",
                0,
            ),
        ],
    )
    def test_toggle_scenarios_parametrized(self, text, start_row, end_row, expected_text, expected_col):
        """Test various toggle scenarios mimicking selection behavior."""
        new_text, col = toggle_comment_lines(text, start_row, end_row)
        assert new_text == expected_text
        assert col == expected_col


class TestSelectionCommentBehavior:
    """Tests verifying how selection-based commenting behaves.

    These tests document the current behavior: line comments operate on
    ENTIRE lines, regardless of column positions in the selection.
    """

    def test_partial_selection_comments_entire_lines(self):
        """Selecting from middle of line 0 to middle of line 1 comments both entire lines.

        Example: selecting "CT *\nFROM" from "SELECT *\nFROM users"
        (col 4 of line 0 to col 4 of line 1) should still comment both full lines.
        """
        text = "SELECT *\nFROM users"

        # Simulating selection from (row=0, col=4) to (row=1, col=4)
        # This is what action_gc_selection does - it only uses the row numbers
        start_row = 0
        end_row = 1

        new_text, col = toggle_comment_lines(text, start_row, end_row)

        # Both ENTIRE lines should be commented, not just the selected portion
        assert new_text == "-- SELECT *\n-- FROM users"
        assert col == 3

    def test_selection_ending_at_line_start_excludes_that_line(self):
        """If selection ends at column 0 of a line, that line should be excluded.

        Example: selecting all of line 0 and ending at start of line 1
        should only comment line 0.
        """
        text = "SELECT *\nFROM users\nWHERE id = 1"

        # Selection from (0, 0) to (1, 0) - ends at very start of line 1
        # action_gc_selection has special handling: end_col == 0 means exclude that line
        start_row = 0
        end_row = 0  # Would be decremented from 1 to 0 in action_gc_selection

        new_text, col = toggle_comment_lines(text, start_row, end_row)

        # Only line 0 should be commented
        assert new_text == "-- SELECT *\nFROM users\nWHERE id = 1"
