"""ER diagram layout engine for terminal rendering."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TableBox:
    """A rendered table box with position and content."""

    name: str
    schema: str
    columns: list[tuple[str, str, bool, bool]]  # (name, type, is_pk, is_fk)
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    def compute_dimensions(self) -> None:
        name_len = len(self.name) + 2
        col_widths = [len(f" {c[0]}  {c[1]} ") + (3 if c[2] or c[3] else 0) for c in self.columns]
        content_width = max([name_len, *col_widths]) if col_widths else name_len
        self.width = content_width + 2  # borders
        self.height = len(self.columns) + 3  # top border + title + separator + columns + bottom border
        if not self.columns:
            self.height = 3


@dataclass
class Relationship:
    """A foreign key relationship between two tables."""

    source_table: str
    source_column: str
    target_table: str
    target_column: str


@dataclass
class DiagramLayout:
    """Computed diagram layout ready for rendering."""

    tables: dict[str, TableBox] = field(default_factory=dict)
    relationships: list[Relationship] = field(default_factory=list)
    width: int = 0
    height: int = 0


def build_layout(
    tables: dict[str, list[tuple[str, str, bool]]],  # name -> [(col_name, col_type, is_pk)]
    foreign_keys: list[tuple[str, str, str, str]],  # [(src_table, src_col, tgt_table, tgt_col)]
    schemas: dict[str, str] | None = None,
) -> DiagramLayout:
    """Build a diagram layout from table and FK data."""
    layout = DiagramLayout()

    fk_lookup: set[tuple[str, str]] = set()
    for src_table, src_col, _tgt_table, _tgt_col in foreign_keys:
        fk_lookup.add((src_table, src_col))

    for table_name, columns in tables.items():
        box = TableBox(
            name=table_name,
            schema=(schemas or {}).get(table_name, ""),
            columns=[
                (col_name, col_type, is_pk, (table_name, col_name) in fk_lookup)
                for col_name, col_type, is_pk in columns
            ],
        )
        box.compute_dimensions()
        layout.tables[table_name] = box

    for src_table, src_col, tgt_table, tgt_col in foreign_keys:
        if src_table in layout.tables and tgt_table in layout.tables:
            layout.relationships.append(
                Relationship(src_table, src_col, tgt_table, tgt_col)
            )

    _position_tables(layout)
    return layout


def _position_tables(layout: DiagramLayout) -> None:
    """Position tables in a grid layout, placing related tables near each other."""
    if not layout.tables:
        return

    adjacency: dict[str, set[str]] = {t: set() for t in layout.tables}
    for rel in layout.relationships:
        adjacency[rel.source_table].add(rel.target_table)
        adjacency[rel.target_table].add(rel.source_table)

    ordered = _topo_order(layout.tables.keys(), adjacency)

    h_gap = 6
    v_gap = 2
    max_cols = _pick_grid_cols(len(ordered))

    row_x = 0
    row_y = 0
    col_idx = 0
    row_max_h = 0

    for table_name in ordered:
        box = layout.tables[table_name]
        box.x = row_x
        box.y = row_y
        row_x += box.width + h_gap
        row_max_h = max(row_max_h, box.height)
        col_idx += 1
        if col_idx >= max_cols:
            col_idx = 0
            row_x = 0
            row_y += row_max_h + v_gap
            row_max_h = 0

    max_x = max(b.x + b.width for b in layout.tables.values())
    max_y = max(b.y + b.height for b in layout.tables.values())
    layout.width = max_x + 1
    layout.height = max_y + 1


def _topo_order(
    tables: object,
    adjacency: dict[str, set[str]],
) -> list[str]:
    """Order tables so that related tables appear near each other (BFS from most-connected)."""
    table_list = list(tables)  # type: ignore[arg-type]
    if not table_list:
        return []

    table_list.sort(key=lambda t: len(adjacency.get(t, set())), reverse=True)

    visited: set[str] = set()
    result: list[str] = []
    queue: list[str] = []

    for start in table_list:
        if start in visited:
            continue
        queue.append(start)
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            result.append(current)
            neighbors = sorted(adjacency.get(current, set()), key=lambda t: len(adjacency.get(t, set())), reverse=True)
            for neighbor in neighbors:
                if neighbor not in visited:
                    queue.append(neighbor)

    return result


def _pick_grid_cols(count: int) -> int:
    if count <= 2:
        return count
    if count <= 4:
        return 2
    if count <= 9:
        return 3
    return 4


def render_diagram(layout: DiagramLayout) -> list[str]:
    """Render the diagram layout to a list of text lines."""
    if not layout.tables:
        return ["(no tables)"]

    canvas_h = layout.height + 4
    canvas_w = layout.width + 10
    canvas: list[list[str]] = [[" "] * canvas_w for _ in range(canvas_h)]

    for box in layout.tables.values():
        _draw_table_box(canvas, box)

    for ri, rel in enumerate(layout.relationships):
        _draw_relationship(canvas, layout, rel, ri)

    return ["".join(row).rstrip() for row in canvas]


def _draw_table_box(canvas: list[list[str]], box: TableBox) -> None:
    """Draw a single table box onto the canvas."""
    x, y, w = box.x, box.y, box.width

    _put(canvas, y, x, "╭")
    _put(canvas, y, x + w - 1, "╮")
    for i in range(1, w - 1):
        _put(canvas, y, x + i, "─")

    title = f" {box.name} "
    title_start = x + 1
    for i, ch in enumerate(title[:w - 2]):
        _put(canvas, y, title_start + i, ch)

    sep_y = y + 1
    _put(canvas, sep_y, x, "├")
    _put(canvas, sep_y, x + w - 1, "┤")
    for i in range(1, w - 1):
        _put(canvas, sep_y, x + i, "─")

    for ci, (col_name, col_type, is_pk, is_fk) in enumerate(box.columns):
        row_y = y + 2 + ci
        _put(canvas, row_y, x, "│")
        _put(canvas, row_y, x + w - 1, "│")

        tag = ""
        if is_pk and is_fk:
            tag = "◆ "  # PK+FK
        elif is_pk:
            tag = "● "  # PK
        elif is_fk:
            tag = "○ "  # FK

        cell = f" {tag}{col_name}  {col_type}"
        cell = cell[:w - 2].ljust(w - 2)
        for i, ch in enumerate(cell):
            _put(canvas, row_y, x + 1 + i, ch)

    bottom_y = y + box.height - 1
    _put(canvas, bottom_y, x, "╰")
    _put(canvas, bottom_y, x + w - 1, "╯")
    for i in range(1, w - 1):
        _put(canvas, bottom_y, x + i, "─")


def _draw_relationship(
    canvas: list[list[str]],
    layout: DiagramLayout,
    rel: Relationship,
    index: int = 0,
) -> None:
    """Draw a relationship line between two table boxes."""
    src_box = layout.tables.get(rel.source_table)
    tgt_box = layout.tables.get(rel.target_table)
    if not src_box or not tgt_box:
        return

    src_col_idx = _find_column_index(src_box, rel.source_column)
    tgt_col_idx = _find_column_index(tgt_box, rel.target_column)
    if src_col_idx < 0 or tgt_col_idx < 0:
        return

    src_row = src_box.y + 2 + src_col_idx
    tgt_row = tgt_box.y + 2 + tgt_col_idx
    offset = index % 3

    if src_box.x + src_box.width <= tgt_box.x:
        src_x = src_box.x + src_box.width
        tgt_x = tgt_box.x - 1
        _draw_line_between(canvas, src_x, src_row, tgt_x, tgt_row, offset)
    elif tgt_box.x + tgt_box.width <= src_box.x:
        src_x = src_box.x - 1
        tgt_x = tgt_box.x + tgt_box.width
        _draw_line_between(canvas, src_x, src_row, tgt_x, tgt_row, offset)
    else:
        sx = src_box.x + src_box.width
        tx = tgt_box.x + tgt_box.width
        mid_x = max(sx, tx) + 1 + offset
        _draw_line_between(canvas, sx, src_row, tx, tgt_row, offset, mid_x)


def _draw_line_between(
    canvas: list[list[str]],
    src_x: int,
    src_y: int,
    tgt_x: int,
    tgt_y: int,
    offset: int = 0,
    force_mid_x: int | None = None,
) -> None:
    """Draw a line from (src_x, src_y) to (tgt_x, tgt_y) with a vertical segment."""
    if src_y == tgt_y:
        lo, hi = min(src_x, tgt_x), max(src_x, tgt_x)
        for x in range(lo, hi + 1):
            _put_line(canvas, src_y, x, "─")
        return

    if force_mid_x is not None:
        mid_x = force_mid_x
    else:
        mid_x = (src_x + tgt_x) // 2 + offset

    h_char = "─"

    if src_x <= mid_x:
        for x in range(src_x, mid_x):
            _put_line(canvas, src_y, x, h_char)
    else:
        for x in range(mid_x + 1, src_x + 1):
            _put_line(canvas, src_y, x, h_char)

    if src_y < tgt_y:
        corner_src = "╮" if src_x <= mid_x else "╭"
        corner_tgt = "╰" if tgt_x >= mid_x else "╯"
        _put_line(canvas, src_y, mid_x, corner_src)
        for y in range(src_y + 1, tgt_y):
            _put_line(canvas, y, mid_x, "│")
        _put_line(canvas, tgt_y, mid_x, corner_tgt)
    else:
        corner_src = "╯" if src_x <= mid_x else "╰"
        corner_tgt = "╭" if tgt_x >= mid_x else "╮"
        _put_line(canvas, src_y, mid_x, corner_src)
        for y in range(tgt_y + 1, src_y):
            _put_line(canvas, y, mid_x, "│")
        _put_line(canvas, tgt_y, mid_x, corner_tgt)

    if tgt_x >= mid_x:
        for x in range(mid_x + 1, tgt_x + 1):
            _put_line(canvas, tgt_y, x, h_char)
    else:
        for x in range(tgt_x, mid_x):
            _put_line(canvas, tgt_y, x, h_char)


def _find_column_index(box: TableBox, column_name: str) -> int:
    for i, (name, _type, _pk, _fk) in enumerate(box.columns):
        if name == column_name:
            return i
    return -1


def _put(canvas: list[list[str]], row: int, col: int, ch: str) -> None:
    if 0 <= row < len(canvas) and 0 <= col < len(canvas[row]):
        canvas[row][col] = ch


_BOX_CHARS = frozenset("╭╮╰╯├┤│─●○◆")


def _put_line(canvas: list[list[str]], row: int, col: int, ch: str) -> None:
    if 0 <= row < len(canvas) and 0 <= col < len(canvas[row]):
        existing = canvas[row][col]
        if existing == " ":
            canvas[row][col] = ch
        elif existing in _BOX_CHARS:
            pass
        elif existing.isalnum() or existing in ("_", "(", ")", ","):
            pass
