from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import (
    Header, Footer, Input, DataTable, ListView, ListItem, Label,
)

from tuney import library


class MenuScreen(Screen):
    """The first thing the user sees: pick an action."""

    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield ListView(
            ListItem(Label("Search library"), id="search"),
            ListItem(Label("Quit"), id="quit"),
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.id == "search":
            self.app.push_screen(SearchScreen())
        elif event.item.id == "quit":
            self.app.exit()


class SearchScreen(Screen):
    """Your original screen, now reachable from the menu."""

    BINDINGS = [
        ("escape", "back", "Back to menu"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="Search your library…")
        yield DataTable()
        yield Footer()

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


class TuneyApp(App):
    CSS = "DataTable { height: 1fr; }"

    def on_mount(self) -> None:
        self.push_screen(MenuScreen())


if __name__ == "__main__":
    TuneyApp().run()