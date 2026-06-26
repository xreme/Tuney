from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.widgets import Header, Footer, ListView, ListItem, Label, RichLog
from textual.containers import Container
from rich.text import Text
from tuney import library

from pathlib import Path

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
    .hidden { display: none; }
ListView { height: 1fr; }
RichLog { height: 1fr; }
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