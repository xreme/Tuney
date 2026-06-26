from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Input, DataTable
from tuney import library
class SearchModal(ModalScreen):
    """"""

    CSS = """
    SearchModal{ align: center middle; }
    #search-dialog {
        width: 80%;
        height: 50%;
        border: solid $accent;
        background: $surface;
    }
    """

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