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

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable()
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(DataTable).add_columns("Artist", "Title", "Album","Year", " Format")

        table = self.query_one(DataTable)
        table.clear()
        for item in library.all_items():
            table.add_row(item.artist, item.title, item.album, item.year, item.format)

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_find(self) -> None:
        self.app.push_screen(SearchModal())