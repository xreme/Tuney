from textual.app import App, ComposeResult
from textual.screen import Screen, ModalScreen
from textual.widgets import (
    Header, Footer, Input, DataTable, ListView, ListItem, Label, RichLog,
)
from rich.text import Text
from textual.containers import Container

from tuney import library

from pathlib import Path


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

class SearchScreen(Screen):
    """"""

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

class CollectionScreen(Screen):
    """"""

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

class ScanModal(ModalScreen):
    CSS = """
    ScanModal { align: center middle; }
    #scan-dialog {
        width: 80%;
        height: 60%;
        border: solid $accent;
        background: $surface;
        padding: 1;
    }
    """

    BINDINGS = [
        ("escape", "back", "Back"),
        ("right", "expand", "Expand"),
        ("left", "go_up", "Up"),
    ]

    def compose(self) -> ComposeResult:
        self._current_dir = Path.cwd()
        self._subdirs: list[Path] = []
        with Container(id="scan-dialog"):
            yield ListView()
            yield RichLog(id="scan-log", wrap=True, classes="hidden")

    def on_mount(self) -> None:
        self._populate_list(self._current_dir)
        self.query_one(ListView).focus()

    def _populate_list(self, directory: Path) -> None:
        self._current_dir = directory
        self._subdirs = sorted(
            p for p in directory.iterdir() if p.is_dir() and not p.name.startswith(".")
        )
        list_view = self.query_one(ListView)
        list_view.clear()
        for d in self._subdirs:
            list_view.append(ListItem(Label(d.name)))

    def action_expand(self) -> None:
        list_view = self.query_one(ListView)
        if list_view.index is not None:
            self._populate_list(self._subdirs[list_view.index])

    def action_go_up(self) -> None:
        parent = self._current_dir.parent
        if parent != self._current_dir:
            self._populate_list(parent)

    def on_list_view_selected(self, _event: ListView.Selected) -> None:
        index = self.query_one(ListView).index
        music_dir = str(self._subdirs[index])
        self.query_one(ListView).display = False
        self.query_one(RichLog).remove_class("hidden")
        self.run_worker(lambda: self._run_scan(music_dir), thread=True)

    def _run_scan(self, music_dir: str) -> None:
        log = self.query_one(RichLog)
        for line in library.scan_stream(music_dir):
            self.app.call_from_thread(log.write, line)
        self.app.call_from_thread(log.write, Text.from_markup("[bold green]Done.[/bold green]"))

    def action_back(self) -> None:
        self.app.pop_screen()

class TuneyApp(App):
    CSS = "DataTable { height: 1fr; } .hidden { display: none; }"

    def on_mount(self) -> None:
        self.push_screen(MenuScreen())


if __name__ == "__main__":
    TuneyApp().run()