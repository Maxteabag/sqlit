"""Tests for JSON tree viewer functionality."""

from __future__ import annotations

from sqlit.shared.ui.widgets_json_tree import parse_json_value


class TestParseJsonValue:
    """Tests for the parse_json_value function that gates JSON tree view."""

    def test_valid_json_object(self):
        """Valid JSON object should be detected and parsed."""
        is_json, parsed = parse_json_value('{"name": "test", "count": 42}')
        assert is_json is True
        assert parsed == {"name": "test", "count": 42}

    def test_valid_json_array(self):
        """Valid JSON array should be detected and parsed."""
        is_json, parsed = parse_json_value('[1, 2, 3]')
        assert is_json is True
        assert parsed == [1, 2, 3]

    def test_python_dict_single_quotes(self):
        """Python dict with single quotes should be parsed via ast.literal_eval."""
        is_json, parsed = parse_json_value("{'key': 'value'}")
        assert is_json is True
        assert parsed == {"key": "value"}

    def test_plain_text_not_json(self):
        """Plain text should not be detected as JSON."""
        is_json, parsed = parse_json_value("hello world")
        assert is_json is False
        assert parsed is None

    def test_malformed_json_not_detected(self):
        """Malformed JSON should not be detected as JSON."""
        is_json, parsed = parse_json_value('{"unclosed": ')
        assert is_json is False
        assert parsed is None

    def test_empty_string(self):
        """Empty string should not be detected as JSON."""
        is_json, parsed = parse_json_value("")
        assert is_json is False
        assert parsed is None

    def test_whitespace_only(self):
        """Whitespace-only string should not be detected as JSON."""
        is_json, parsed = parse_json_value("   \n\t  ")
        assert is_json is False
        assert parsed is None
