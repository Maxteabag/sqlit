"""Tests for query alert classification."""

from sqlit.domains.query.app.alerts import (
    AlertMode,
    AlertSeverity,
    classify_query_alert,
    should_confirm,
)


def test_classify_delete_only() -> None:
    assert classify_query_alert("DELETE FROM users") == AlertSeverity.DELETE


def test_classify_write_keywords() -> None:
    assert classify_query_alert("INSERT INTO t VALUES (1)") == AlertSeverity.WRITE
    assert classify_query_alert("UPDATE t SET a = 1") == AlertSeverity.WRITE
    assert classify_query_alert("CREATE TABLE t (id INT)") == AlertSeverity.WRITE
    assert classify_query_alert("DROP TABLE t") == AlertSeverity.WRITE
    assert classify_query_alert("TRUNCATE TABLE t") == AlertSeverity.WRITE
    assert classify_query_alert("ALTER TABLE t ADD COLUMN a INT") == AlertSeverity.WRITE
    assert classify_query_alert("RENAME TABLE t TO t2") == AlertSeverity.WRITE


def test_classify_read_only() -> None:
    assert classify_query_alert("SELECT * FROM users") == AlertSeverity.NONE


def test_classify_multi_statement_escalation() -> None:
    sql = "SELECT 1; DELETE FROM users;"
    assert classify_query_alert(sql) == AlertSeverity.DELETE


def test_comments_and_literals_ignored() -> None:
    assert classify_query_alert("SELECT '-- DELETE'") == AlertSeverity.NONE
    assert classify_query_alert("SELECT 1 /* DELETE */") == AlertSeverity.NONE
    assert classify_query_alert("-- DELETE\nSELECT 1") == AlertSeverity.NONE


def test_should_confirm_modes() -> None:
    assert should_confirm(AlertMode.DELETE, AlertSeverity.DELETE) is True
    assert should_confirm(AlertMode.DELETE, AlertSeverity.WRITE) is False
    assert should_confirm(AlertMode.WRITE, AlertSeverity.WRITE) is True
    assert should_confirm(AlertMode.WRITE, AlertSeverity.DELETE) is True
    assert should_confirm(AlertMode.OFF, AlertSeverity.DELETE) is False
