"""Bound routine-name work without weakening completion/disambiguation behavior."""
from sqlit.domains.connections.providers.adapters.base import RoutineInfo
from sqlit.domains.query.completion import get_completions


def test_routine_completion_does_not_rescan_catalog_per_candidate():
    class CountedRoutine(RoutineInfo):
        conversions = 0

        def __str__(self):
            type(self).conversions += 1
            return super().__str__()

    count = 500
    routines = [CountedRoutine(f"proc_{i:04d}", schema="dbo", database="lab") for i in range(count)]
    sql = "EXEC proc_"
    suggestions = get_completions(sql, len(sql), [], {}, routines)
    assert suggestions == [f"proc_{i:04d}" for i in range(50)]
    assert CountedRoutine.conversions < count * 15


def test_routine_disambiguation_keeps_database_schema_and_original_case():
    routines = [
        RoutineInfo("RunReport", schema="sales", database="first"),
        RoutineInfo("RunReport", schema="sales", database="second"),
        RoutineInfo("RunReport", schema="ops", database="first"),
        RoutineInfo("UniqueReport", schema="sales", database="first"),
    ]
    sql = "EXEC "
    suggestions = get_completions(sql, len(sql), [], {}, routines)
    assert set(suggestions) == {"first.sales.RunReport", "second.sales.RunReport", "first.ops.RunReport", "UniqueReport"}


def test_blank_completion_does_not_read_routine_catalog():
    class UnreadableRoutine(str):
        def __str__(self):
            raise AssertionError("Blank SQL must not inspect routines")

    assert get_completions(" \n", 2, [], {}, [UnreadableRoutine("anything")]) == []
