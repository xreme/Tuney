from textual.widgets import DataTable

from tuney import library
from tuney.tui.Modals import ConvertModal
from .CollectionPane import CollectionPane


class ConvertPane(CollectionPane):
    """Mark tracks for conversion in bulk, then convert the marked set. Marks
    survive filtering and sorting, so a set can be built across searches."""

    PANE_NAME = "Convert"

    COLUMNS = [
        ("✓", "mark"),
        ("Artist", "artist"),
        ("Title", "title"),
        ("Album", "album"),
        ("Format", "format"),
        ("ID", "id"),
    ]

    FIXED_WIDTHS = {"mark": 3, "format": 8, "id": 6}

    BINDINGS = [
        ("escape", "clear_filter", "Clear filter"),
        ("/", "find", "Filter"),
        ("space", "toggle_mark", "Mark"),
        ("a", "mark_all", "Mark all shown"),
        ("x", "clear_marks", "Clear marks"),
        ("c", "convert", "Convert marked"),
    ]

    MARKED = "✓"
    UNMARKED = "·"

    def __init__(self, leaf=None) -> None:
        super().__init__(leaf)
        self._marked: set[int] = set()

    # ---- marks -------------------------------------------------------------

    def _cell(self, item, field):
        if field == "mark":
            return self.MARKED if item.id in self._marked else self.UNMARKED
        return super()._cell(item, field)

    def _visible_items(self):
        # Sorting by the checkbox column means "marked first"; the parent would
        # try to read a `mark` attribute off the beets item and fail.
        if self._sort_field != "mark":
            return super()._visible_items()
        saved, self._sort_field = self._sort_field, None
        try:
            items = super()._visible_items()
        finally:
            self._sort_field = saved
        return sorted(items, key=lambda item: item.id not in self._marked,
                      reverse=self._sort_reverse)

    def _update_subtitle(self) -> None:
        shown, total = len(self._visible), len(self._items)
        scope = f"{shown} of {total} items" if shown != total else f"{total} items"
        self.border_subtitle = (f"{len(self._marked)} marked · {scope}"
                                if self._marked else scope)

    def _refresh_rows(self) -> None:
        super()._refresh_rows()
        self._update_subtitle()

    def _redraw_mark(self, row: int, item) -> None:
        # One checkbox rather than a full repopulate; marking happens dozens of
        # times in a row.
        table = self._table()
        if table is None:
            return
        try:
            table.update_cell_at((row, 0), self._cell(item, "mark"))
        except Exception:
            self._refresh_rows()
        else:
            self._update_subtitle()

    # ---- actions -----------------------------------------------------------

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        # Enter marks the row instead of opening it; details stay in the
        # collection pane.
        self._toggle_row(event.cursor_row)

    def _toggle_row(self, row: int | None) -> None:
        if row is None or not 0 <= row < len(self._visible):
            return
        item = self._visible[row]
        if item.id in self._marked:
            self._marked.discard(item.id)
        else:
            self._marked.add(item.id)
        self._redraw_mark(row, item)

    def action_toggle_mark(self) -> None:
        table = self._table()
        if table is not None:
            self._toggle_row(table.cursor_row)

    def action_mark_all(self) -> None:
        self._marked.update(item.id for item in self._visible)
        self._refresh_rows()
        self.notify(f"{len(self._marked)} tracks marked for conversion.")

    def action_clear_marks(self) -> None:
        if not self._marked:
            return
        self._marked.clear()
        self._refresh_rows()

    def action_convert(self) -> None:
        if not self._marked:
            self.notify("Mark some tracks first — space marks the highlighted "
                        "one, 'a' marks everything shown.", severity="warning")
            return
        count = len(self._marked)
        self.app.push_screen(
            ConvertModal(query=library.ids_query(self._marked),
                         scope_label=f"{count} marked "
                                     f"{'track' if count == 1 else 'tracks'}"),
            self._on_converted)

    def _on_converted(self, _result=None) -> None:
        # Replace mode repoints library entries at new files, so re-read.
        self._marked.clear()
        self.reload()
