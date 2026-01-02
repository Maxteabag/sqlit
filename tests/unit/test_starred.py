"""Tests for starred queries store."""

from __future__ import annotations

import json

import pytest

from sqlit.domains.query.store.starred import StarredStore


@pytest.fixture
def starred_store(tmp_path):
    """Create a StarredStore with a temporary file."""
    store = StarredStore()
    store._file_path = tmp_path / "starred_queries.json"
    return store


class TestStarredStore:
    """Tests for StarredStore functionality."""

    def test_star_query(self, starred_store):
        """Test starring a query."""
        result = starred_store.star_query("test-conn", "SELECT * FROM users")
        assert result is True
        assert starred_store.is_starred("test-conn", "SELECT * FROM users")

    def test_star_query_already_starred(self, starred_store):
        """Test starring an already starred query returns False."""
        starred_store.star_query("test-conn", "SELECT * FROM users")
        result = starred_store.star_query("test-conn", "SELECT * FROM users")
        assert result is False

    def test_unstar_query(self, starred_store):
        """Test unstarring a query."""
        starred_store.star_query("test-conn", "SELECT * FROM users")
        result = starred_store.unstar_query("test-conn", "SELECT * FROM users")

        assert result is True
        assert not starred_store.is_starred("test-conn", "SELECT * FROM users")

    def test_unstar_query_not_starred(self, starred_store):
        """Test unstarring a query that wasn't starred returns False."""
        result = starred_store.unstar_query("test-conn", "SELECT * FROM users")
        assert result is False

    def test_toggle_star_stars(self, starred_store):
        """Test toggling star on unstarred query stars it."""
        result = starred_store.toggle_star("test-conn", "SELECT 1")
        assert result is True
        assert starred_store.is_starred("test-conn", "SELECT 1")

    def test_toggle_star_unstars(self, starred_store):
        """Test toggling star on starred query unstars it."""
        starred_store.star_query("test-conn", "SELECT 1")
        result = starred_store.toggle_star("test-conn", "SELECT 1")
        assert result is False
        assert not starred_store.is_starred("test-conn", "SELECT 1")

    def test_queries_stripped(self, starred_store):
        """Test that queries are normalized (stripped)."""
        starred_store.star_query("test-conn", "  SELECT 1  ")
        assert starred_store.is_starred("test-conn", "SELECT 1")
        assert starred_store.is_starred("test-conn", "  SELECT 1  ")

    def test_load_for_connection(self, starred_store):
        """Test loading starred queries for a connection."""
        starred_store.star_query("conn1", "SELECT 1")
        starred_store.star_query("conn1", "SELECT 2")
        starred_store.star_query("conn2", "SELECT 3")

        starred = starred_store.load_for_connection("conn1")
        assert starred == {"SELECT 1", "SELECT 2"}

        starred = starred_store.load_for_connection("conn2")
        assert starred == {"SELECT 3"}

    def test_load_for_connection_empty(self, starred_store):
        """Test loading starred queries for a connection with no starred queries."""
        starred = starred_store.load_for_connection("nonexistent")
        assert starred == set()

    def test_is_starred_different_connections(self, starred_store):
        """Test that starred queries are per-connection."""
        starred_store.star_query("conn1", "SELECT 1")

        assert starred_store.is_starred("conn1", "SELECT 1")
        assert not starred_store.is_starred("conn2", "SELECT 1")

    def test_clear_for_connection(self, starred_store):
        """Test clearing all starred queries for a connection."""
        starred_store.star_query("conn1", "SELECT 1")
        starred_store.star_query("conn1", "SELECT 2")
        starred_store.star_query("conn2", "SELECT 3")

        count = starred_store.clear_for_connection("conn1")

        assert count == 2
        assert starred_store.load_for_connection("conn1") == set()
        assert starred_store.load_for_connection("conn2") == {"SELECT 3"}

    def test_clear_for_connection_empty(self, starred_store):
        """Test clearing for a connection with no starred queries."""
        count = starred_store.clear_for_connection("nonexistent")
        assert count == 0

    def test_persistence(self, starred_store):
        """Test that starred queries are persisted to disk."""
        starred_store.star_query("conn1", "SELECT 1")
        starred_store.star_query("conn1", "SELECT 2")

        # Create new store pointing to same file
        new_store = StarredStore()
        new_store._file_path = starred_store._file_path

        starred = new_store.load_for_connection("conn1")
        assert starred == {"SELECT 1", "SELECT 2"}

    def test_json_structure(self, starred_store):
        """Test the JSON file structure."""
        starred_store.star_query("conn1", "SELECT 1")
        starred_store.star_query("conn2", "SELECT 2")

        with open(starred_store._file_path) as f:
            data = json.load(f)

        assert data == {
            "conn1": ["SELECT 1"],
            "conn2": ["SELECT 2"],
        }

    def test_unstar_removes_empty_connection(self, starred_store):
        """Test that unstarring the last query removes the connection from JSON."""
        starred_store.star_query("conn1", "SELECT 1")
        starred_store.unstar_query("conn1", "SELECT 1")

        with open(starred_store._file_path) as f:
            data = json.load(f)

        assert "conn1" not in data
