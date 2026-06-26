from textual.screen import Screen
from textual.app import ComposeResult
from tuney import library
from textual.widgets import Input, DataTable
from textual.containers import Container

class SearchScreen(Screen):
    """Let User serach for music"""

    BINDINGS = [
        ("escape", "back", "Back to menu"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="search-dialog"):
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

    def action_back(self) -> None:
        self.app.pop_screen()
