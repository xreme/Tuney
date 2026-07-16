import os

from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.widgets import Button, Label, Static
from textual.containers import Container, Horizontal
from rich.text import Text

from tuney import library


class ConfirmModal(ModalScreen[bool]):
    """Approve/reject dialog for a tool call paused by the HITL middleware.

    Dismisses with True (approve) or False (reject). Escape rejects, so an
    abandoned dialog never silently approves a destructive action.
    """

    CSS = """
    ConfirmModal { align: center middle; }
    #confirm-dialog {
        width: 60%;
        max-width: 80;
        height: auto;
        border: solid $warning;
        background: $surface;
        padding: 1 2;
    }
    #modal-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }
    #confirm-detail {
        width: 100%;
        padding-bottom: 1;
    }
    #confirm-buttons {
        width: 100%;
        height: auto;
        align-horizontal: center;
    }
    #confirm-buttons Button { margin: 0 2; }
    """

    BINDINGS = [
        ("escape", "reject", "Reject"),
        ("y", "approve", "Approve"),
        ("n", "reject", "Reject"),
    ]

    def __init__(self, request: dict) -> None:
        super().__init__()
        self._request = request

    TITLE_STYLE = "bold cyan"
    ALBUM_STYLE = "italic magenta"
    PATH_STYLE = "yellow"

    def _describe(self) -> Text | None:
        """Human-friendly text for known tools; None falls back to the raw view."""
        if self._request.get("name") != "remove_item":
            return None
        args = self._request.get("args", {})
        title = f"item {args.get('item_id')}"
        artist = album = path = None
        try:
            item = library.get_item(args.get("item_id"))
        except Exception:
            item = None
        if item is not None:
            fields = dict(item)
            title = str(fields.get("title") or title)
            artist = str(fields.get("artist") or "") or None
            album = str(fields.get("album") or "") or None
            if item.path:
                path = os.fsdecode(item.path)

        delete = bool(args.get("delete_file"))
        text = Text()
        text.append("Tuney would like to permanently delete " if delete
                    else "Tuney would like to remove ")
        text.append(title, style=self.TITLE_STYLE)
        if artist:
            text.append(f" by {artist}")
        if album:
            text.append(" from the album ")
            text.append(album, style=self.ALBUM_STYLE)
        if delete:
            text.append(".\n\n")
            if path:
                text.append("File: ")
                text.append(path, style=self.PATH_STYLE)
                text.append("\n\n")
            text.append("The audio file will be deleted from disk — this cannot be undone.")
        else:
            text.append(" from your library.\n\nThe audio file will stay on disk.")
        return text

    def compose(self) -> ComposeResult:
        detail = self._describe()
        if detail is None:
            args = ", ".join(f"{k}={v!r}" for k, v in self._request.get("args", {}).items())
            detail = Text(f"{self._request.get('description') or 'Tool requires approval'}\n\n"
                          f"  {self._request.get('name', '?')}({args})")
        with Container(id="confirm-dialog"):
            yield Label("Tuney needs your approval", id="modal-title")
            yield Static(detail, id="confirm-detail")
            with Horizontal(id="confirm-buttons"):
                yield Button("Approve (y)", id="approve", variant="error")
                yield Button("Reject (n)", id="reject", variant="primary")
            yield Label(r"\[y] approve | \[n]/\[esc] reject", id="modal-hint")

    def on_mount(self) -> None:
        self.query_one("#reject", Button).focus()   # safe default

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "approve")

    def action_approve(self) -> None:
        self.dismiss(True)

    def action_reject(self) -> None:
        self.dismiss(False)
