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
