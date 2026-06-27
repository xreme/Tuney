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

    #modal-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }

        #hint{
        width: 100%;
        text-align: center;
    }

    ListView > ListItem.-highlight {
        background: $accent 30%;
        color: $text;
    }
    """

    BINDINGS = [
        ("escape", "back", "Back"),
        ("right", "expand", "Open"),
        ("left", "go_up", "Up"),
        ("S", "scan_current", "Scan this folder"),
    ]

    def compose(self) -> ComposeResult:
        self._current_dir = Path.cwd()
        self._subdirs: list[Path] = []
        self._nav_dirs: list[Path] = []
        with Container(id="scan-dialog"):
            yield Label("Scan Directory", id="modal-title")
            yield Label("Enter opens a folder · Shift+S scans this one", id="hint")
            yield Label(self._current_dir.name+"/", id="dir_label")
            yield ListView()
            yield RichLog(id="scan-log", wrap=True, classes="hidden")

            yield Label(r"\[←]\[→] navigate | \[enter] open | \[shift+S] scan this folder | \[esc] close ", id="modal-hint")

    async def on_mount(self) -> None:
        await self._populate_list(self._current_dir)

    async def _populate_list(self, directory: Path) -> None:
        self._current_dir = directory
        self.query_one("#dir_label", Label).update(str(directory))
        self._subdirs = sorted(
            p for p in directory.iterdir() if p.is_dir() and not p.name.startswith(".")
        )
        # Row 0 navigates to the parent; rows 1..N map to self._subdirs.
        self._nav_dirs = [directory.parent, *self._subdirs]

        list_view = self.query_one(ListView)
        await list_view.clear()

        items = [ListItem(Label("../"))]
        items += [ListItem(Label(d.name + "/")) for d in self._subdirs]
        file_count = len([i for i in directory.iterdir() if i.is_file()])
        if file_count > 0:
            items.append(ListItem(Label(f"(+{file_count} Files)")))
        await list_view.extend(items)

        list_view.index = 1 if self._subdirs else 0
        list_view.focus()

    async def _open_highlighted(self) -> None:
        index = self.query_one(ListView).index
        if index is not None and index < len(self._nav_dirs):
            await self._populate_list(self._nav_dirs[index])

    async def on_list_view_selected(self, _event: ListView.Selected) -> None:
        await self._open_highlighted()

    async def action_expand(self) -> None:
        await self._open_highlighted()

    async def action_go_up(self) -> None:
        parent = self._current_dir.parent
        if parent != self._current_dir:
            await self._populate_list(parent)

    def action_scan_current(self) -> None:
        self._start_scan(str(self._current_dir))

    def _start_scan(self, music_dir: str) -> None:
        self.query_one(ListView).display = False
        self.query_one(RichLog).remove_class("hidden")
        self.run_worker(lambda: self._run_scan(music_dir), thread=True)

    def _run_scan(self, music_dir: str) -> None:
        log = self.query_one(RichLog)
        for line in library.scan_stream(music_dir):
            self.app.call_from_thread(log.write, line)
        self.app.call_from_thread(log.write, Text.from_markup(r"[bold green]Done. Press \[ESC] to Close.[/bold green]"))

    def action_back(self) -> None:
        self.app.pop_screen()