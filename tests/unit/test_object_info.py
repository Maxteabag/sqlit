"""Unit tests for explorer object info helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderMetadata
from sqlit.domains.explorer.domain.tree_nodes import ProcedureNode
from sqlit.domains.explorer.ui.tree import object_info


class FakeProvider:
    def __init__(self, db_type: str):
        self.metadata = ProviderMetadata(
            db_type=db_type,
            display_name=db_type,
            badge_label=db_type,
            default_port="3306",
            supports_ssh=False,
            is_file_based=False,
            has_advanced_auth=False,
            requires_auth=True,
            url_schemes=(),
        )


def _make_host() -> MagicMock:
    host = MagicMock()
    host.current_provider = DatabaseProvider(
        metadata=FakeProvider("mysql").metadata,
        schema=None,  # type: ignore[arg-type]
        capabilities=None,  # type: ignore[arg-type]
        driver=None,
        connection_factory=None,  # type: ignore[arg-type]
        query_executor=None,  # type: ignore[arg-type]
        schema_inspector=None,  # type: ignore[arg-type]
        dialect=None,  # type: ignore[arg-type]
        config_validator=None,  # type: ignore[arg-type]
        docker_detector=None,
        explorer_nodes=None,  # type: ignore[arg-type]
        display_info=lambda _: "",
        apply_database_override=lambda c, _: c,
        post_connect=lambda _a, _b: None,
        post_connect_warnings=lambda _: [],
        get_auth_type=lambda _: None,
    )
    return host


def test_show_procedure_info_loads_editable_definition_for_mysql() -> None:
    """MySQL procedure DDL is loaded into the editor wrapped in DELIMITER blocks."""
    host = _make_host()
    schema_service = MagicMock()
    schema_service.get_procedure_definition.return_value = {
        "name": "my_proc",
        "schema": "mydb",
        "language": "SQL",
        "definition": "CREATE PROCEDURE `my_proc`() BEGIN SELECT 1; END",
    }
    host._get_schema_service.return_value = schema_service

    object_info.show_procedure_info(host, ProcedureNode(database="mydb", name="my_proc"))

    schema_service.get_procedure_definition.assert_called_once_with("mydb", "my_proc")
    text = host.query_input.text
    assert text.startswith("DROP PROCEDURE IF EXISTS `my_proc`;")
    assert "DELIMITER $$" in text
    assert "CREATE PROCEDURE `my_proc`()" in text
    assert "$$\nDELIMITER ;" in text
    host._replace_results_table.assert_called_once()


def test_show_procedure_info_not_supported() -> None:
    """Unsupported provider shows a warning instead of crashing."""
    host = _make_host()
    schema_service = MagicMock()
    schema_service.get_procedure_definition.return_value = None
    host._get_schema_service.return_value = schema_service

    object_info.show_procedure_info(host, ProcedureNode(database="mydb", name="my_proc"))

    host.notify.assert_called_once()
    assert "warning" in host.notify.call_args.kwargs.get("severity", "")


def test_show_procedure_info_error_handling() -> None:
    """Errors during definition retrieval are surfaced to the user."""
    host = _make_host()
    schema_service = MagicMock()
    schema_service.get_procedure_definition.side_effect = RuntimeError("boom")
    host._get_schema_service.return_value = schema_service

    object_info.show_procedure_info(host, ProcedureNode(database="mydb", name="my_proc"))

    host.notify.assert_called_once()
    assert "error" in host.notify.call_args.kwargs.get("severity", "")


def test_index_definition_is_wrapped_in_comment() -> None:
    """Non-editable object definitions stay wrapped in a comment block."""
    host = _make_host()
    object_info.display_object_info(
        host,
        "Index",
        {"name": "IX_Test", "definition": "CREATE INDEX IX_Test ON t(c)"},
    )
    assert host.query_input.text == "/*\nCREATE INDEX IX_Test ON t(c)\n*/"
