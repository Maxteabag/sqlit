"""Tests for schema-change detection used to refresh the explorer."""

from __future__ import annotations

from sqlit.domains.query.ui.mixins.query_execution import _sql_changes_schema


def test_create_table_triggers_refresh() -> None:
    assert _sql_changes_schema("CREATE TABLE users (id INT);") is True


def test_alter_table_triggers_refresh() -> None:
    assert _sql_changes_schema("ALTER TABLE users ADD name VARCHAR(50);") is True


def test_drop_table_triggers_refresh() -> None:
    assert _sql_changes_schema("DROP TABLE users;") is True


def test_create_procedure_does_not_trigger_refresh() -> None:
    assert _sql_changes_schema("CREATE PROCEDURE p() BEGIN SELECT 1; END;") is False


def test_create_procedure_with_definer_does_not_trigger_refresh() -> None:
    sql = """DROP PROCEDURE IF EXISTS `p`;
DELIMITER $$
CREATE DEFINER=`root`@`%` PROCEDURE `p`()
BEGIN
    SELECT 1;
END $$
DELIMITER ;"""
    assert _sql_changes_schema(sql) is False


def test_drop_procedure_does_not_trigger_refresh() -> None:
    assert _sql_changes_schema("DROP PROCEDURE IF EXISTS p;") is False


def test_alter_procedure_does_not_trigger_refresh() -> None:
    assert _sql_changes_schema("ALTER PROCEDURE p SQL SECURITY INVOKER;") is False


def test_create_function_does_not_trigger_refresh() -> None:
    assert _sql_changes_schema("CREATE FUNCTION f() RETURNS INT BEGIN RETURN 1; END;") is False


def test_create_trigger_does_not_trigger_refresh() -> None:
    assert _sql_changes_schema("CREATE TRIGGER tr BEFORE INSERT ON t FOR EACH ROW SET NEW.x = 1;") is False


def test_create_event_does_not_trigger_refresh() -> None:
    assert _sql_changes_schema("CREATE EVENT ev ON SCHEDULE EVERY 1 HOUR DO SELECT 1;") is False


def test_mixed_ddl_triggers_refresh() -> None:
    """If a batch contains both procedure and table DDL, refresh the explorer."""
    sql = """
    DROP PROCEDURE IF EXISTS p;
    CREATE TABLE new_table (id INT);
    """
    assert _sql_changes_schema(sql) is True


def test_select_does_not_trigger_refresh() -> None:
    assert _sql_changes_schema("SELECT * FROM users;") is False


def test_insert_does_not_trigger_refresh() -> None:
    assert _sql_changes_schema("INSERT INTO users VALUES (1);") is False
