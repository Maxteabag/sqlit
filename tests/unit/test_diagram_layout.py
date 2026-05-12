"""Tests for ER diagram layout engine."""

from __future__ import annotations

from sqlit.domains.diagram.app.layout import (
    DiagramLayout,
    TableBox,
    build_layout,
    render_diagram,
)


class TestTableBox:
    def test_compute_dimensions_basic(self) -> None:
        box = TableBox(
            name="users",
            schema="",
            columns=[("id", "int", True, False), ("name", "varchar", False, False)],
        )
        box.compute_dimensions()
        assert box.width > 0
        assert box.height == 5  # top + title_sep + 2 cols + bottom

    def test_compute_dimensions_empty_table(self) -> None:
        box = TableBox(name="empty", schema="", columns=[])
        box.compute_dimensions()
        assert box.width > 0
        assert box.height == 3  # top + title_sep + bottom


class TestBuildLayout:
    def test_single_table(self) -> None:
        tables = {"users": [("id", "int", True), ("name", "varchar", False)]}
        layout = build_layout(tables, [])
        assert "users" in layout.tables
        assert layout.tables["users"].x == 0
        assert layout.tables["users"].y == 0

    def test_two_related_tables(self) -> None:
        tables = {
            "orders": [("id", "int", True), ("user_id", "int", False)],
            "users": [("id", "int", True), ("name", "varchar", False)],
        }
        fks = [("orders", "user_id", "users", "id")]
        layout = build_layout(tables, fks)
        assert len(layout.tables) == 2
        assert len(layout.relationships) == 1

    def test_fk_marks_column_as_fk(self) -> None:
        tables = {
            "orders": [("id", "int", True), ("user_id", "int", False)],
            "users": [("id", "int", True)],
        }
        fks = [("orders", "user_id", "users", "id")]
        layout = build_layout(tables, fks)
        order_cols = layout.tables["orders"].columns
        assert order_cols[1][3] is True  # user_id is_fk

    def test_ignores_fks_for_missing_tables(self) -> None:
        tables = {"users": [("id", "int", True)]}
        fks = [("orders", "user_id", "users", "id")]
        layout = build_layout(tables, fks)
        assert len(layout.relationships) == 0

    def test_grid_layout_positions(self) -> None:
        tables = {f"t{i}": [("id", "int", True)] for i in range(6)}
        layout = build_layout(tables, [])
        positions = {name: (box.x, box.y) for name, box in layout.tables.items()}
        # All positions should be unique
        assert len(set(positions.values())) == 6


class TestRenderDiagram:
    def test_empty_tables(self) -> None:
        layout = DiagramLayout()
        lines = render_diagram(layout)
        assert lines == ["(no tables)"]

    def test_renders_table_box(self) -> None:
        tables = {"users": [("id", "int", True), ("name", "varchar", False)]}
        layout = build_layout(tables, [])
        lines = render_diagram(layout)
        text = "\n".join(lines)
        assert "users" in text
        assert "●" in text  # PK indicator
        assert "id" in text
        assert "name" in text

    def test_renders_fk_indicator(self) -> None:
        tables = {
            "orders": [("id", "int", True), ("user_id", "int", False)],
            "users": [("id", "int", True)],
        }
        fks = [("orders", "user_id", "users", "id")]
        layout = build_layout(tables, fks)
        lines = render_diagram(layout)
        text = "\n".join(lines)
        assert "○" in text  # FK indicator

    def test_renders_relationship_lines(self) -> None:
        tables = {
            "orders": [("id", "int", True), ("user_id", "int", False)],
            "users": [("id", "int", True)],
        }
        fks = [("orders", "user_id", "users", "id")]
        layout = build_layout(tables, fks)
        lines = render_diagram(layout)
        text = "\n".join(lines)
        # Should contain relationship line characters
        assert any(ch in text for ch in "─│╮╯╰╭◀")
