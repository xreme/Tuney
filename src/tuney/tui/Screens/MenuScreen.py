from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Header, Footer, ListView, ListItem, Label
from tuney.tui.Screens import CollectionScreen, ChatScreen, SettingScreen
from tuney.tui.Modals import ScanModal

class MenuScreen(Screen):
    """The first thing the user sees: pick an action."""

    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield ListView(
            ListItem(Label("View Collection"), id="collection"),
            ListItem(Label("Chat"), id="chat"),
            ListItem(Label("Scan Directory"), id="scan"),
            ListItem(Label("Settings"), id="settings"),
            ListItem(Label("Quit"), id="quit"),
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.id == "collection":
            self.app.push_screen(CollectionScreen())
        elif event.item.id == "chat":
            self.app.push_screen(ChatScreen())
        elif event.item.id == "scan":
            self.app.push_screen(ScanModal())
        elif event.item.id == "settings":
            self.app.push_screen(SettingScreen())
        elif event.item.id == "quit":
            self.app.exit()