"""Regression coverage for dialect-specific identity completion."""

import pytest

from sqlit.domains.query.completion import get_completions, postgres_identity


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


@pytest.mark.parametrize(
    "earlier_statement",
    ["", "CREATE TABLE genres (id INT);\n", "ALTER TABLE genres ADD id INT;\n", "-- CREATE\n"],
)
@pytest.mark.parametrize("prefix", ["g", "ge", "gen", "q"])
def test_ordinary_postgres_select_skips_identity_tokenization(monkeypatch, earlier_statement, prefix):
    def unexpected_tokenization(_sql):
        pytest.fail("SELECT reached the PostgreSQL identity scanner")

    monkeypatch.setattr(postgres_identity, "_scan_context", unexpected_tokenization)
    history = "SELECT id, title FROM books WHERE id = 12345;\n" * 250
    sql = earlier_statement + history + f"SELECT * FROM {prefix}"
    tables = ["gadgets", "geographies", "genres", "quotes", "books"]
    assert get_completions(sql, len(sql), tables, {}, dialect="postgresql") == get_completions(
        sql, len(sql), tables, {}
    )


@pytest.mark.parametrize(
    ("query", "identity"),
    [
        ("SELECT 1; -- publisher's schema ; (\nCREATE TABLE t (id INT GE|);", True),
        ("/* publisher's schema ; ( */ CREATE TABLE t (id INT GEN|);", True),
        ("CREATE TABLE t (x TEXT, -- publisher's id ; (\n id INT GEN|);", True),
        ("CREATE TABLE t (x TEXT,/* outer /* inner */ ; ' ( */ id INT GEN|);", True),
        ("ALTER TABLE t ADD x TEXT, /* publisher's id ; ( */ ADD id INT GEN|;", True),
        ('CREATE TABLE "/*t*/" ("--id" INT GEN|);', True),
        ("CREATE TABLE t (x TEXT DEFAULT '/* ; (, */ -- ''', id INT GEN|);", True),
        ("CREATE TABLE t (x TEXT DEFAULT $body$/* '; (, --$body$, id INT GEN|);", True),
        (r"CREATE TABLE t (x TEXT DEFAULT E'a\'; /*', id INT GEN|);", True),
        ("SELECT '/*'; CREATE TABLE t (id INT GEN|);", True),
        ("CREATE TABLE t (id INT/* explanation */GEN|);", True),
        ("CREATE TABLE t (id INT-- explanation\r\nGEN|);", True),
        ("CREATE TABLE t (id pg_catalog.int8 NOT NULL UNIQUE GEN|);", True),
        ("SELECT 2 # 1; CREATE TABLE t (id INT GEN|);", True),
        ("SELECT '$💡$'; CREATE TABLE t (id INT GEN|);", True),
        ("SELECT value$💡$; CREATE TABLE t (id INT GEN|);", True),
        ("SELECT E'a'\n'\\'; hidden'; CREATE TABLE t (id INT GEN|);", True),
        ("SELECT E'a'\n'\\'; CREATE TABLE t (id INT GEN|);';", False),
        ("-- ; CREATE TABLE t (id INT GEN|\n", False),
        ("/* outer /* inner */ ; CREATE TABLE t (id INT GEN|); */", False),
        ("SELECT 'text ; CREATE TABLE t (id INT GEN|);';", False),
        (r"SELECT E'a\'; CREATE TABLE t (id INT GEN|);';", False),
        ("CREATE TABLE t (id INT CHECK (id BIGINT GEN|));", False),
        ("CREATE TABLE t (id TEXT GEN|);", False),
        ("CREATE TABLE t (id INT); SELECT * FROM gen|", False),
        ("SELECT 1 GEN|; CREATE TABLE t (id INT);", False),
    ],
)
def test_identity_completion_uses_sql_context_before_cursor(query, identity):
    before, after = query.split("|")
    suggestions = get_completions(before + after, len(before), [], {}, dialect="postgresql")
    assert ("GENERATED ALWAYS AS IDENTITY" in suggestions) is identity


@pytest.mark.parametrize("tag", ["", "body", "💡", "a\u0301"])
@pytest.mark.parametrize("closed", [False, True])
def test_identity_completion_respects_dollar_quote_boundaries(tag, closed):
    delimiter = f"${tag}$"
    ddl = "CREATE TABLE t (id INT GEN"
    sql = f"SELECT {delimiter}; {ddl}"
    if closed:
        sql += f"); {delimiter}; {ddl}"
        after = ");"
    else:
        after = f"); {delimiter};"
    completion = get_completions(sql + after, len(sql), [], {}, dialect="postgresql")
    assert ("GENERATED ALWAYS AS IDENTITY" in completion) is closed
