"""Explicit lab-only interventions; never imported by the production app."""
from __future__ import annotations


def install_variant(name: str) -> None:
    if name.startswith("chunk"):
        from sqlit.domains.query.ui.mixins import query_results
        query_results.RESULTS_RENDER_CHUNK_SIZE = int(name.removeprefix("chunk"))
    elif name == "widthcache":
        from textual_fastdatatable.backend import ArrowBackend
        original = ArrowBackend.append_rows
        def append(self, records):
            before = self.row_count
            widths = list(self._column_content_widths)
            result = original(self, records)
            if widths:
                delta = ArrowBackend(self.data.slice(before))
                delta.render_markup = self.render_markup
                self._column_content_widths = [max(a,b) for a,b in zip(widths, delta.column_content_widths)]
            return result
        ArrowBackend.append_rows = append
    elif name == "preview-thread":
        import asyncio

        from textual_fastdatatable.backend import ArrowBackend

        from sqlit.domains.query.ui.mixins.query_results import QueryResultsMixin
        from sqlit.shared.ui.widgets_tables import _stringify_uuid_rows
        def schedule(self, table, columns, rows, *, escape, start_index, row_limit, render_token, **kwargs):
            def prepare():
                backend = ArrowBackend.from_records(_stringify_uuid_rows(rows[:row_limit]), column_names=columns)
                backend.render_markup = not escape
                backend.column_content_widths  # measure before returning to UI thread
                return backend
            async def finish():
                backend = await asyncio.to_thread(prepare)
                if render_token != self._results_render_token:
                    return
                ready = self._build_results_table(columns, [], escape=escape, backend=backend)
                info = getattr(table, "result_table_info", None)
                if info is not None:
                    ready.result_table_info = info
                self._replace_results_table_with_table(ready)
            self._results_render_worker = self.run_worker(finish(), exclusive=True, group="lab-render")
        QueryResultsMixin._schedule_results_render = schedule
    elif name == "idle-demand":
        from sqlit.domains.shell.app.idle_scheduler import IdleScheduler
        original_schedule = IdleScheduler._schedule_check
        original_request = IdleScheduler.request_idle_callback
        original_check = IdleScheduler._check_and_work
        def schedule(self):
            if self._queue and self._timer is None:
                original_schedule(self)
        def request(self, *a, **kw):
            result = original_request(self, *a, **kw)
            self._schedule_check()
            return result
        def check(self):
            self._timer = None
            original_check(self)
        IdleScheduler._schedule_check = schedule
        IdleScheduler.request_idle_callback = request
        IdleScheduler._check_and_work = check
    elif name == "no-blink":
        from sqlit.shared.ui.widgets_text_area import QueryTextArea
        original_init = QueryTextArea.__init__
        def init(self, *a, **kw):
            original_init(self, *a, **kw)
            self.cursor_blink = False
        QueryTextArea.__init__ = init
    elif name.startswith("timer"):
        from sqlit.domains.query.ui.mixins import query_results
        from sqlit.domains.shell.app.idle_scheduler import IdleScheduler
        query_results.RESULTS_RENDER_CHUNK_SIZE = int(name.removeprefix("timer"))
        original_request = IdleScheduler.request_idle_callback
        def request(self, callback, *a, **kw):
            if kw.get("name") == "results-render":
                self.app.set_timer(.001, callback)
                return True
            return original_request(self, callback, *a, **kw)
        IdleScheduler.request_idle_callback = request
    elif name == "clipcells":
        from rich.text import Text
        from textual.coordinate import Coordinate

        from sqlit.shared.ui.widgets_tables import SqlitDataTable
        original = SqlitDataTable._get_cell_renderable
        def render(self,row_index,column_index,max_width=None):
            if row_index>=0 and max_width and not self.render_markup:
                value=self.get_cell_at(Coordinate(row_index,column_index))
                if isinstance(value,str) and len(value)>max_width and '\n' not in value and '\r' not in value:
                    text=Text(value,no_wrap=True)
                    text.truncate(max_width,overflow="ellipsis")
                    return text
            return original(self,row_index,column_index,max_width)
        SqlitDataTable._get_cell_renderable = render
