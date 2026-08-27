"""Regression coverage for SQL query formatting."""

from __future__ import annotations

import pytest

from sqlit.domains.query.editing.formatting import format_sql, remap_cursor_after_format


def test_formats_complex_query_consistently() -> None:
    query = (
        "select u.id,u.name,count(o.id) as orders from users u "
        "left join orders o on o.user_id=u.id where u.active=true "
        "group by u.id,u.name order by orders desc"
    )

    assert format_sql(query) == """SELECT u.id,
       u.name,
       count(o.id) AS orders
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
WHERE u.active = TRUE
GROUP BY u.id,
         u.name
ORDER BY orders DESC"""


def test_preserves_comments_and_string_contents() -> None:
    formatted = format_sql("-- keep this\nselect 'from where' as phrase, a from t -- tail")

    assert formatted.startswith("-- keep this")
    assert "'from where'" in formatted
    assert formatted.endswith("FROM t -- tail")


def test_preserves_named_and_positional_placeholders() -> None:
    formatted = format_sql("select * from users where id=:id and name=%s")

    assert "id = :id" in formatted
    assert "name = %s" in formatted


def test_preserves_postgres_json_operators() -> None:
    formatted = format_sql("select payload->>'name' from events where payload ? 'name'")

    assert "payload ->> 'name'" in formatted
    assert "payload ? 'name'" in formatted


def test_preserves_mssql_bracketed_identifiers_and_hints() -> None:
    formatted = format_sql(
        "select top (10) [User Name],isnull(score,0) from [dbo].[Users] with (nolock)"
    )

    assert "[User Name]" in formatted
    assert "[dbo].[Users] WITH (nolock)" in formatted


def test_preserves_semicolon_statement_boundaries() -> None:
    formatted = format_sql("select 1;select 2;")

    assert formatted == "SELECT 1;\n\nSELECT 2;"


def test_preserves_double_blank_line_statement_boundaries() -> None:
    formatted = format_sql("select a,b from one\n\n\nselect c,d from two")

    assert "FROM one\n\n\nSELECT c" in formatted
    assert "FROM two" in formatted


@pytest.mark.parametrize("query", ["", "   ", "\n\t\n"])
def test_empty_or_whitespace_only_query_is_unchanged(query: str) -> None:
    assert format_sql(query) == query


def test_formatting_is_idempotent() -> None:
    once = format_sql("select id,name from users where active=true")

    assert format_sql(once) == once


@pytest.mark.parametrize(
    ("query", "cursor", "expected_token"),
    [
        ("select id,name from users", (0, 6), "SELECT"),
        ("select id,name from users", (0, 14), "name"),
        ("select id,name from users", (0, 25), "users"),
    ],
)
def test_cursor_stays_beside_same_token(
    query: str,
    cursor: tuple[int, int],
    expected_token: str,
) -> None:
    formatted = format_sql(query)
    row, column = remap_cursor_after_format(query, formatted, cursor)
    lines = formatted.splitlines()

    assert lines[row][:column].endswith(expected_token)
