from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, DataTable
from tuney import library


class TuneyApp(App):
    CSS = "DataTable { height: 1fr; }"
    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="Search your library…")
        yield DataTable()

    def on_mount(self) -> None:
        self.query_one(DataTable).add_columns("Artist", "Title", "Album")
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        table = self.query_one(DataTable)
        table.clear()
        for item in library.search(event.value):
            table.add_row(item.artist, item.title, item.album)