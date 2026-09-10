"""Read-only UI experiment: retain Python rows, sample widths, normalize on read.

This is NOT a drop-in production backend. DataTable export/mutation support and
exact column widths are deliberately outside this rendering experiment.
"""
from __future__ import annotations

from textual_fastdatatable.backend import _measure_width

from sqlit.shared.ui.widgets_tables import normalize_arrow_value


class RowBackend:
    def __init__(self, rows, columns):
        self.data = rows
        self.columns = list(columns)
        self.render_markup = False
        self._widths = None

    @property
    def row_count(self):
        return len(self.data)

    @property
    def source_row_count(self):
        return self.row_count

    @property
    def column_count(self):
        return len(self.columns)

    @property
    def column_content_widths(self):
        if self._widths is None:
            sample = [*self.data[:128], *self.data[-1:]]
            self._widths = [0]*self.column_count
            for row in sample:
                for col,value in enumerate(row):
                    value = normalize_arrow_value(value)
                    if isinstance(value,str) and value.isascii() and '\n' not in value and '\r' not in value:
                        size = min(len(value),100)
                    else:
                        size = min(_measure_width(value,render_markup=False),100)
                    self._widths[col] = max(self._widths[col],size)
        return self._widths

    def get_cell_at(self,row_index,column_index):
        return normalize_arrow_value(self.data[row_index][column_index])

    def get_row_at(self,index):
        return [normalize_arrow_value(value) for value in self.data[index]]

    def get_column_at(self,index):
        return [normalize_arrow_value(row[index]) for row in self.data]
