from os import fsdecode
from os.path import basename

from textual import work
from textual.app import ComposeResult
from textual.widgets import DataTable, Input
from tuney import library
from tuney.tui.Modals import TrackDetailModal
from .base import Pane


class CollectionPane(Pane):
    """Browse and filter the user's collection."""

    PANE_NAME = "Collection"

    DEFAULT_CSS = """
    CollectionPane #filter {
        dock: top;
        border: tall $accent;
    }
    CollectionPane DataTable {
        height: 1fr;
    }
    """

    BINDINGS = [
        ("escape", "clear_filter", "Clear filter"),
        ("/", "find", "Filter"),
    ]

    # (label, item attribute) for each column, in display order.
    COLUMNS = [
        ("Artist", "artist"),
        ("Title", "title"),
        ("Album", "album"),
        ("Year", "year"),
        ("Format", "format"),
        ("ID", "id"),
    ]

    # Fixed widths for the narrow columns; the three text columns share the rest.
    YEAR_WIDTH = 6
    FORMAT_WIDTH = 8
    ID_WIDTH = 6
    MIN_TEXT_WIDTH = 8

    # Rows go into the table in slices this big, yielding to the event loop
    # between slices: the table measures every new cell in a single idle pass,
    # so adding a large library in one go freezes the whole app for seconds.
    ROW_CHUNK = 500
    # Refilter only once typing pauses; each pass rebuilds the whole table.
    FILTER_DEBOUNCE = 0.2

    def __init__(self, leaf=None) -> None:
        super().__init__(leaf)
        self._items = []
        self._visible = []
        self._sort_field = None
        self._sort_reverse = False
        self._populate_gen = 0
        self._filter_timer = None

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Filter by artist, title or album…", id="filter")
        yield DataTable()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        self._build_columns()
        self.border_subtitle = "loading…"
        # Load off the UI thread — a full library read takes hundreds of ms
        # and this runs on every pane rebuild, not just launch.
        self.reload()

        # Size the columns once the table has a real width.
        self.call_after_refresh(self._fit_columns)

    def focus_pane(self) -> None:
        self.query_one(DataTable).focus()

    @work(thread=True, exclusive=True)
    def reload(self) -> None:
        """Re-read the library (after a scan/import/retag may have changed
        it). The read and change-check run in a thread — a full library read
        takes hundreds of ms, far too long to block the UI on every modal
        close. Skips the refresh when nothing visible changed so the table
        keeps its cursor and scroll position."""
        if not self.is_mounted:        # nothing to update yet
            return
        items = library.all_items()
        if self._fingerprint(items) == self._fingerprint(self._items):
            return
        self.app.call_from_thread(self._apply_items, items)

    def _apply_items(self, items) -> None:
        self._items = items
        self._refresh_rows()

    def _fingerprint(self, items) -> list[tuple]:
        """Identity plus every displayed field, so metadata edits count as
        changes even though the track ids stay the same."""
        return [(item.id, *(getattr(item, field) for _, field in self.COLUMNS))
                for item in items]

    def on_resize(self) -> None:
        self._fit_columns()

    def _build_columns(self) -> None:
        """(Re)create the columns, marking the sorted one with an arrow."""
        table = self.query_one(DataTable)
        table.clear(columns=True)
        self._text_keys = []
        for label, field in self.COLUMNS:
            if field == self._sort_field:
                label += " ▼" if self._sort_reverse else " ▲"
            if field == "year":
                table.add_column(label, width=self.YEAR_WIDTH)
            elif field == "format":
                table.add_column(label, width=self.FORMAT_WIDTH)
            elif field == "id":
                table.add_column(label, width=self.ID_WIDTH)
            else:
                self._text_keys.append(table.add_column(label))

    def _cell(self, item, field):
        """Display value for one cell, with fallbacks for missing metadata."""
        value = getattr(item, field)
        if field == "title" and not value:
            return basename(fsdecode(item.path))
        if field in ("artist", "album") and not value:
            return "Unknown"
        return value

    def _visible_items(self):
        items = self._items
        query = self.query_one("#filter", Input).value.strip().lower()
        if query:
            # Every word must appear somewhere in the row's text.
            def matches(item):
                haystack = " ".join(
                    str(self._cell(item, field)) for _, field in self.COLUMNS
                ).lower()
                return all(word in haystack for word in query.split())
            items = [item for item in items if matches(item)]

        if self._sort_field:
            def sort_key(item):
                value = getattr(item, self._sort_field)
                return value.lower() if isinstance(value, str) else value
            items = sorted(items, key=sort_key, reverse=self._sort_reverse)
        return items

    def _refresh_rows(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        items = self._visible_items()
        self._visible = items          # row index -> item, for row selection
        if len(items) == len(self._items):
            self.border_subtitle = f"{len(self._items)} items"
        else:
            self.border_subtitle = f"{len(items)} of {len(self._items)} items"
        self._populate_gen += 1
        self._add_rows_from(self._populate_gen, 0)

    def _add_rows_from(self, generation: int, start: int) -> None:
        """Add one chunk of rows and reschedule for the rest, so the screen
        paints and keys keep working while a big table fills in. A newer
        refresh bumps the generation, cancelling any population in flight."""
        if generation != self._populate_gen or not self.is_mounted:
            return
        table = self.query_one(DataTable)
        for item in self._visible[start:start + self.ROW_CHUNK]:
            table.add_row(*(self._cell(item, field) for _, field in self.COLUMNS))
        if start + self.ROW_CHUNK < len(self._visible):
            self.call_after_refresh(
                self._add_rows_from, generation, start + self.ROW_CHUNK)

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._filter_timer is not None:
            self._filter_timer.stop()
        self._filter_timer = self.set_timer(self.FILTER_DEBOUNCE, self._refresh_rows)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.query_one(DataTable).focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if 0 <= event.cursor_row < len(self._visible):
            self.app.push_screen(TrackDetailModal(self._visible[event.cursor_row]))

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        field = self.COLUMNS[event.column_index][1]
        if field == self._sort_field:
            if self._sort_reverse:
                # Third click clears the sort back to library order.
                self._sort_field = None
                self._sort_reverse = False
            else:
                self._sort_reverse = True
        else:
            self._sort_field = field
            self._sort_reverse = False
        self._build_columns()
        self._refresh_rows()
        self._fit_columns()

    def _fit_columns(self) -> None:
        """Give Artist/Title/Album equal widths that fill the visible table."""
        table = self.query_one(DataTable)
        pad = table.cell_padding * 2                 # padding per column (both sides)

        # Space to render into, minus a little slack for the scrollbar/borders.
        available = table.size.width - 2
        if available <= 0:
            return

        # Render width consumed by the fixed columns (value + padding).
        fixed = ((self.YEAR_WIDTH + pad) + (self.FORMAT_WIDTH + pad)
                 + (self.ID_WIDTH + pad))
        # Remaining space, split evenly across the three text columns' content.
        each = max(self.MIN_TEXT_WIDTH, (available - fixed) // 3 - pad)

        for key in self._text_keys:
            column = table.columns[key]
            column.auto_width = False
            column.width = each

        table._require_update_dimensions = True

    def action_clear_filter(self) -> None:
        filter_input = self.query_one("#filter", Input)
        if filter_input.value:
            filter_input.value = ""
        self.query_one(DataTable).focus()

    def action_find(self) -> None:
        self.query_one("#filter", Input).focus()
