from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Header, Footer, ListView, ListItem, Label
from tuney.tui.Screens import SearchScreen, CollectionScreen
from tuney.tui.Modals import ScanModal

class MenuScreen(Screen):
    """The first thing the user sees: pick an action."""

    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield ListView(
            ListItem(Label("View Collection"), id="collection"),
            ListItem(Label("Search library"), id="search"),
            ListItem(Label("Scan Directory"), id="scan"),
            ListItem(Label("Quit"), id="quit"),
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.id == "search":
            self.app.push_screen(SearchScreen())
        elif event.item.id == "collection":
            self.app.push_screen(CollectionScreen())
        elif event.item.id == "scan":
            self.app.push_screen(ScanModal())
            # library.scan("./")
        elif event.item.id == "quit":
            self.app.exit()