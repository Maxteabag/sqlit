"""Regression coverage for dialect-specific identity completion."""

import pytest

from sqlit.domains.query.completion import get_completions
from sqlit.domains.query.completion import postgres_identity


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("CREATE TABLE books (id BIGINT GEN", "GENERATED ALWAYS AS IDENTITY"),
        ("ALTER TABLE books ADD COLUMN id INT GENERATED ", "ALWAYS AS IDENTITY"),
        ("CREATE TABLE books (id BIGINT GENERATED\nBY DEFAULT AS I", "IDENTITY"),
    ],
)
def test_identity_completion_is_postgresql_only(sql, expected):
    assert expected in get_completions(sql, len(sql), [], {}, dialect="postgresql")
    assert get_completions(sql, len(sql), [], {}, dialect="sqlite") == get_completions(
        sql, len(sql), [], {}
    )


def test_ordinary_postgres_select_skips_identity_tokenization(monkeypatch):
    def unexpected_tokenization(_sql):
        pytest.fail("SELECT without an identity prefix reached the identity lexer")

    monkeypatch.setattr(postgres_identity, "tokenize", unexpected_tokenization)
    sql = "SELECT * FROM books WHERE title = "
    assert get_completions(sql, len(sql), [], {}, dialect="postgresql") == get_completions(
        sql, len(sql), [], {}
    )
