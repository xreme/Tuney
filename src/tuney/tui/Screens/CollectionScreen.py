from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Header,Footer,DataTable
from tuney.tui.Modals.SearchModal import SearchModal
from tuney import library

class CollectionScreen(Screen):
    """Display the User's Collection"""

    BINDINGS = [
        ("escape", "back", "Back to menu"),
        ("q", "quit", "Quit"),
        ("/", "find", "Find"),
    ]

    # Fixed widths for the narrow columns; the three text columns share the rest.
    YEAR_WIDTH = 4
    FORMAT_WIDTH = 6
    MIN_TEXT_WIDTH = 8

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable()
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        self._artist = table.add_column("Artist")
        self._title = table.add_column("Title")
        self._album = table.add_column("Album")
        table.add_column("Year", width=self.YEAR_WIDTH)
        table.add_column("Format", width=self.FORMAT_WIDTH)

        for item in library.all_items():
            table.add_row(item.artist, item.title, item.album, item.year, item.format)

        # Size the columns once the table has a more width
        self.call_after_refresh(self._fit_columns)

    def on_resize(self) -> None:
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

        for key in (self._artist, self._title, self._album):
            column = table.columns[key]
            column.auto_width = False
            column.width = each

        table._require_update_dimensions = True

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_find(self) -> None:
        self.app.push_screen(SearchModal())
