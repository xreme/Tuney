from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Header, Footer, DataTable, Input
from tuney import library

class CollectionScreen(Screen):
    """Display the User's Collection"""

    CSS = """
    #filter {
        dock: top;
        border: tall $accent;
    }
    """

    BINDINGS = [
        ("escape", "back", "Back to menu"),
        ("q", "quit", "Quit"),
        ("/", "find", "Filter"),
    ]

    # (label, item attribute) for each column, in display order.
    COLUMNS = [
        ("Artist", "artist"),
        ("Title", "title"),
        ("Album", "album"),
        ("Year", "year"),
        ("Format", "format"),
    ]

    # Fixed widths for the narrow columns; the three text columns share the rest.
    YEAR_WIDTH = 6
    FORMAT_WIDTH = 8
    MIN_TEXT_WIDTH = 8

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="Filter by artist, title or album…", id="filter")
        yield DataTable()
        yield Footer()

    def on_mount(self) -> None:
        self._items = library.all_items()
        self._sort_field = None
        self._sort_reverse = False
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        self._build_columns()
        self._refresh_rows()
        table.focus()

        # Size the columns once the table has a real width.
        self.call_after_refresh(self._fit_columns)

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
            else:
                self._text_keys.append(table.add_column(label))

    def _visible_items(self):
        items = self._items
        query = self.query_one("#filter", Input).value.strip().lower()
        if query:
            # Every word must appear somewhere in the row's text.
            def matches(item):
                haystack = " ".join(
                    str(getattr(item, field)) for _, field in self.COLUMNS
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
        for item in items:
            table.add_row(*(getattr(item, field) for _, field in self.COLUMNS))
        if len(items) == len(self._items):
            self.sub_title = f"{len(self._items)} items"
        else:
            self.sub_title = f"{len(items)} of {len(self._items)} items"

    def on_input_changed(self, event: Input.Changed) -> None:
        self._refresh_rows()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.query_one(DataTable).focus()

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

        # Render width consumed by the two fixed columns (value + padding).
        fixed = (self.YEAR_WIDTH + pad) + (self.FORMAT_WIDTH + pad)
        # Remaining space, split evenly across the three text columns' content.
        each = max(self.MIN_TEXT_WIDTH, (available - fixed) // 3 - pad)

        for key in self._text_keys:
            column = table.columns[key]
            column.auto_width = False
            column.width = each

        table._require_update_dimensions = True

    def action_back(self) -> None:
        filter_input = self.query_one("#filter", Input)
        if filter_input.value:
            filter_input.value = ""
            self.query_one(DataTable).focus()
        elif self.focused is filter_input:
            self.query_one(DataTable).focus()
        else:
            self.app.pop_screen()

    def action_find(self) -> None:
        self.query_one("#filter", Input).focus()
