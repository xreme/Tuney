from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Label, ListView, ListItem


class PaneChooserModal(ModalScreen[str | None]):
    """Pick which pane type fills a workspace slot."""

    CSS = """
    PaneChooserModal { align: center middle; }
    #chooser-dialog {
        width: 40;
        height: auto;
        border: solid $accent;
        background: $surface;
        padding: 1;
    }
    #chooser-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }
    ListView { height: auto; }
    ListView > ListItem.-highlight {
        background: $accent 30%;
        color: $text;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    PANES = [
        ("collection", "Collection"),
        ("chat", "Chat"),
        ("settings", "Settings"),
    ]

    def __init__(self, title: str = "New pane") -> None:
        super().__init__()
        self._title = title

    def compose(self) -> ComposeResult:
        with Container(id="chooser-dialog"):
            yield Label(self._title, id="chooser-title")
            yield ListView(
                *(ListItem(Label(label), id=f"choose-{name}")
                  for name, label in self.PANES)
            )

    def on_mount(self) -> None:
        self.query_one(ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.dismiss(event.item.id.removeprefix("choose-"))

    def action_cancel(self) -> None:
        self.dismiss(None)
