"""SQL Server procedure/function autocomplete regressions."""

from unittest.mock import MagicMock

from sqlit.domains.connections.providers.adapters.base import RoutineInfo
from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter
from sqlit.domains.query.completion import get_completions
from sqlit.domains.query.ui.mixins.autocomplete_schema import (
    _completion_routine_loader,
    _dedupe_routines,
)


def _routines() -> list[RoutineInfo]:
    return [
        RoutineInfo(
            "dt_setpropertybyid",
            schema="dbo",
            routine_type="PROCEDURE",
            parameters=("@direction", "@value"),
        ),
        RoutineInfo(
            "fn_score",
            schema="dbo",
            routine_type="FUNCTION",
            return_type="int",
            parameters=("@user_id",),
        ),
        RoutineInfo(
            "fn_orders",
            schema="dbo",
            routine_type="FUNCTION",
            return_type="TABLE",
            parameters=("@user_id",),
        ),
    ]


def test_mssql_loads_routine_types_and_parameters() -> None:
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchall.return_value = [
        ("dbo", "dt_setpropertybyid", "PROCEDURE", None, "@direction", 1),
        ("dbo", "dt_setpropertybyid", "PROCEDURE", None, "@value", 2),
        ("dbo", "fn_orders", "FUNCTION", "TABLE", None, 0),
        ("dbo", "fn_orders", "FUNCTION", "TABLE", "@user_id", 1),
        ("dbo", "fn_score", "FUNCTION", "int", None, 0),
        ("dbo", "fn_score", "FUNCTION", "int", "@user_id", 1),
    ]

    routines = SQLServerAdapter().get_completion_routines(connection, database="AppDB")

    by_name = {str(routine): routine for routine in routines}
    assert by_name["dt_setpropertybyid"].parameters == ("@direction", "@value")
    assert by_name["fn_orders"].is_table_valued is True
    assert by_name["fn_score"].return_type == "INT"
    assert cursor.execute.call_args_list[0].args[0] == "USE [AppDB]"
    assert "INFORMATION_SCHEMA.PARAMETERS" in cursor.execute.call_args_list[1].args[0]


def test_exec_parameter_completion() -> None:
    sql = "EXEC dt_setpropertybyid dir"

    completions = get_completions(sql, len(sql), [], {}, _routines())

    assert completions == ["@direction"]


def test_schema_qualified_exec_parameter_completion() -> None:
    sql = "EXEC dbo.dt_setpropertybyid val"

    completions = get_completions(sql, len(sql), [], {}, _routines())

    assert completions == ["@value"]


def test_schema_qualified_procedure_name_completion() -> None:
    sql = "EXEC dbo.dt_"

    completions = get_completions(sql, len(sql), [], {}, _routines())

    assert completions == ["dt_setpropertybyid"]


def test_schema_qualified_procedure_completion_after_dot() -> None:
    sql = "EXEC dbo."

    completions = get_completions(sql, len(sql), [], {}, _routines())

    assert completions == ["dt_setpropertybyid"]


def test_partially_bracketed_procedure_name_completion() -> None:
    sql = "EXEC [dbo].[dt_"

    completions = get_completions(sql, len(sql), [], {}, _routines())

    assert completions == ["dt_setpropertybyid"]


def test_bracket_qualified_exec_parameter_completion() -> None:
    sql = "EXEC [dbo].[dt_setpropertybyid] dir"

    completions = get_completions(sql, len(sql), [], {}, _routines())

    assert completions == ["@direction"]


def test_later_exec_parameter_completion() -> None:
    sql = "EXEC dt_setpropertybyid @direction = 'up', val"

    completions = get_completions(sql, len(sql), [], {}, _routines())

    assert completions == ["@value"]


def test_parameter_completion_uses_current_exec_statement() -> None:
    routines = _routines() + [
        RoutineInfo(
            "first_proc",
            schema="dbo",
            routine_type="PROCEDURE",
            parameters=("@first_only",),
        )
    ]
    sql = "EXEC first_proc @first_only = 1; EXEC dt_setpropertybyid val"

    completions = get_completions(sql, len(sql), [], {}, routines)

    assert completions == ["@value"]


def test_parameter_completion_after_return_status_assignment() -> None:
    sql = "EXEC @status = dbo.dt_setpropertybyid dir"

    completions = get_completions(sql, len(sql), [], {}, _routines())

    assert completions == ["@direction"]


def test_scalar_function_completion_in_select_expression() -> None:
    sql = "SELECT fn_sc"

    completions = get_completions(sql, len(sql), [], {}, _routines())

    assert "fn_score" in completions
    assert "dt_setpropertybyid" not in completions


def test_table_valued_function_completion_after_from() -> None:
    sql = "SELECT * FROM fn_ord"

    completions = get_completions(sql, len(sql), [], {}, _routines())

    assert "fn_orders" in completions
    assert "fn_score" not in completions


def test_schema_qualified_function_completion() -> None:
    sql = "SELECT dbo.fn_sc"

    completions = get_completions(sql, len(sql), [], {}, _routines())

    assert "fn_score" in completions


def test_schema_qualified_table_function_excludes_scalar_functions() -> None:
    sql = "SELECT * FROM dbo.fn_"

    completions = get_completions(sql, len(sql), [], {}, _routines())

    assert "fn_orders" in completions
    assert "fn_score" not in completions


def test_schema_qualified_table_function_excludes_other_schemas() -> None:
    routines = _routines() + [
        RoutineInfo(
            "fn_sales",
            schema="sales",
            routine_type="FUNCTION",
            return_type="TABLE",
        )
    ]
    sql = "SELECT * FROM dbo.fn_"

    completions = get_completions(sql, len(sql), [], {}, routines)

    assert "fn_orders" in completions
    assert "fn_sales" not in completions


def test_table_alias_dot_does_not_offer_scalar_functions() -> None:
    sql = "SELECT * FROM orders o WHERE o."

    completions = get_completions(
        sql,
        len(sql),
        ["orders"],
        {"orders": ["id", "total"]},
        _routines(),
    )

    assert "id" in completions
    assert "fn_score" not in completions


def test_schema_qualified_apply_excludes_other_schemas() -> None:
    routines = _routines() + [
        RoutineInfo(
            "fn_sales",
            schema="sales",
            routine_type="FUNCTION",
            return_type="TABLE",
        )
    ]
    sql = "SELECT * FROM users CROSS APPLY dbo.fn_"

    completions = get_completions(sql, len(sql), ["users"], {}, routines)

    assert "fn_orders" in completions
    assert "fn_sales" not in completions


def test_bracket_qualified_table_function_excludes_other_schemas() -> None:
    routines = _routines() + [
        RoutineInfo(
            "fn_sales",
            schema="sales",
            routine_type="FUNCTION",
            return_type="TABLE",
        )
    ]
    sql = "SELECT * FROM [dbo].fn_"

    completions = get_completions(sql, len(sql), [], {}, routines)

    assert "fn_orders" in completions
    assert "fn_sales" not in completions


def test_partially_bracketed_table_function_completion() -> None:
    sql = "SELECT * FROM [dbo].[fn_"

    completions = get_completions(sql, len(sql), [], {}, _routines())

    assert "fn_orders" in completions
    assert "fn_score" not in completions


def test_database_qualified_table_function_completion() -> None:
    routines = [
        RoutineInfo(
            "fn_orders",
            database="AppDB",
            schema="dbo",
            routine_type="FUNCTION",
            return_type="TABLE",
        ),
        RoutineInfo(
            "fn_orders",
            database="AuditDB",
            schema="dbo",
            routine_type="FUNCTION",
            return_type="TABLE",
        ),
    ]
    sql = "SELECT * FROM AppDB.dbo.fn_"

    completions = get_completions(sql, len(sql), [], {}, routines)

    assert completions == ["fn_orders"]


def test_database_qualified_scalar_function_completion() -> None:
    routines = [
        RoutineInfo(
            "fn_score",
            database="AppDB",
            schema="dbo",
            routine_type="FUNCTION",
            return_type="INT",
        ),
        RoutineInfo(
            "fn_score",
            database="AuditDB",
            schema="dbo",
            routine_type="FUNCTION",
            return_type="INT",
        ),
    ]
    sql = "SELECT AppDB.dbo.fn_"

    completions = get_completions(sql, len(sql), [], {}, routines)

    assert completions == ["fn_score"]


def test_exec_inside_string_does_not_trigger_parameter_completion() -> None:
    sql = "SELECT 'EXEC dbo.dt_setpropertybyid dir', fn_"

    completions = get_completions(sql, len(sql), [], {}, _routines())

    assert "fn_score" in completions
    assert "@direction" not in completions


def test_exec_inside_comment_does_not_trigger_parameter_completion() -> None:
    sql = "-- EXEC dbo.dt_setpropertybyid dir\nSELECT fn_"

    completions = get_completions(sql, len(sql), [], {}, _routines())

    assert "fn_score" in completions
    assert "@direction" not in completions


def test_semicolon_free_statement_after_exec_uses_new_statement_context() -> None:
    sql = "EXEC dbo.dt_setpropertybyid @direction = 'up'\nSELECT fn_sc"

    completions = get_completions(sql, len(sql), [], {}, _routines())

    assert "fn_score" in completions
    assert "@direction" not in completions


def test_routine_deduplication_preserves_same_name_in_different_schemas() -> None:
    dbo = RoutineInfo(
        "refresh",
        schema="dbo",
        parameters=("@dbo_value",),
    )
    sales = RoutineInfo(
        "refresh",
        schema="sales",
        parameters=("@sales_value",),
    )

    assert _dedupe_routines([dbo, sales, dbo]) == [dbo, sales]


def test_routine_deduplication_preserves_same_name_in_different_databases() -> None:
    app_db = RoutineInfo("refresh", database="AppDB", schema="dbo")
    audit_db = RoutineInfo("refresh", database="AuditDB", schema="dbo")

    assert _dedupe_routines([app_db, audit_db, app_db]) == [app_db, audit_db]


def test_duplicate_cross_database_routines_are_qualified() -> None:
    routines = [
        RoutineInfo("refresh", database="AppDB", schema="dbo"),
        RoutineInfo("refresh", database="AuditDB", schema="dbo"),
    ]
    sql = "EXEC ref"

    completions = get_completions(sql, len(sql), [], {}, routines)

    assert completions == ["AppDB.dbo.refresh", "AuditDB.dbo.refresh"]


def test_database_qualified_parameter_completion() -> None:
    routines = [
        RoutineInfo(
            "refresh",
            database="AppDB",
            schema="dbo",
            parameters=("@app_value",),
        ),
        RoutineInfo(
            "refresh",
            database="AuditDB",
            schema="dbo",
            parameters=("@audit_value",),
        ),
    ]
    sql = "EXEC AuditDB.dbo.refresh audit"

    completions = get_completions(sql, len(sql), [], {}, routines)

    assert completions == ["@audit_value"]


def test_unqualified_cross_schema_routine_requires_qualification() -> None:
    routines = [
        RoutineInfo("refresh", schema="sales", parameters=("@sales_value",)),
        RoutineInfo("refresh", schema="dbo", parameters=("@dbo_value",)),
    ]
    sql = "EXEC refresh dbo"

    completions = get_completions(sql, len(sql), [], {}, routines)

    assert completions == []


def test_unqualified_ambiguous_non_dbo_routine_has_no_parameters() -> None:
    routines = [
        RoutineInfo("refresh", schema="sales", parameters=("@sales_value",)),
        RoutineInfo("refresh", schema="reporting", parameters=("@report_value",)),
    ]
    sql = "EXEC refresh value"

    completions = get_completions(sql, len(sql), [], {}, routines)

    assert completions == []


def test_rich_completion_metadata_uses_separate_cache_key() -> None:
    inspector = MagicMock()
    inspector.get_completion_routines = MagicMock()

    cache_field, loader = _completion_routine_loader(inspector)

    assert cache_field == "completion_routines"
    assert loader is inspector.get_completion_routines


def test_drop_procedure_excludes_functions() -> None:
    sql = "DROP PROCEDURE dt_"

    completions = get_completions(sql, len(sql), [], {}, _routines())

    assert completions == ["dt_setpropertybyid"]


def test_drop_function_excludes_procedures() -> None:
    sql = "DROP FUNCTION fn_"

    completions = get_completions(sql, len(sql), [], {}, _routines())

    assert completions == ["fn_score", "fn_orders"]


def test_plain_legacy_procedures_are_not_scalar_function_suggestions() -> None:
    sql = "SELECT get_"

    completions = get_completions(sql, len(sql), [], {}, ["get_user"])

    assert "get_user" not in completions


def test_include_functions_false_hides_scalar_and_table_functions() -> None:
    select_sql = "SELECT fn_"
    from_sql = "SELECT * FROM fn_"

    assert "fn_score" not in get_completions(
        select_sql,
        len(select_sql),
        [],
        {},
        _routines(),
        include_functions=False,
    )
    assert "fn_orders" not in get_completions(
        from_sql,
        len(from_sql),
        [],
        {},
        _routines(),
        include_functions=False,
    )
