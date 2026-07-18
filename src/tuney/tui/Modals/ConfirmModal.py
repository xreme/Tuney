import os

from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.widgets import Button, Label, Static
from textual.containers import Container, Horizontal, VerticalScroll
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
    #confirm-detail-scroll {
        width: 100%;
        height: auto;
        max-height: 60vh;
        margin-bottom: 1;
    }
    #confirm-detail {
        width: 100%;
        height: auto;
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
        ("up", "scroll_detail(-1)", "Scroll up"),
        ("down", "scroll_detail(1)", "Scroll down"),
        ("pageup", "scroll_detail_page(-1)", "Page up"),
        ("pagedown", "scroll_detail_page(1)", "Page down"),
    ]

    def __init__(self, request: dict) -> None:
        super().__init__()
        self._request = request

    TITLE_STYLE = "bold cyan"
    ALBUM_STYLE = "italic magenta"
    PATH_STYLE = "yellow"

    def _describe(self) -> Text | None:
        """Human-friendly text for known tools; None falls back to the raw view."""
        name = self._request.get("name")
        args = self._request.get("args", {})
        if name == "remove_item":
            return self._describe_item(args.get("item_id"), bool(args.get("delete_file")))
        if name == "remove_items":
            return self._describe_batch(list(args.get("item_ids") or []),
                                        bool(args.get("delete_files")))
        if name == "remove_album":
            return self._describe_album(args.get("album_id"), bool(args.get("delete_files")))
        return None

    @staticmethod
    def _lookup_item(item_id):
        try:
            return library.get_item(item_id)
        except Exception:
            return None

    def _item_fields(self, item_id) -> tuple[str, str | None, str | None, str | None]:
        """(title, artist, album, path) for an id, with fallbacks for bad ids."""
        item = self._lookup_item(item_id)
        if item is None:
            return f"item {item_id}", None, None, None
        fields = dict(item)
        return (
            str(fields.get("title") or f"item {item_id}"),
            str(fields.get("artist") or "") or None,
            str(fields.get("album") or "") or None,
            os.fsdecode(item.path) if item.path else None,
        )

    def _describe_item(self, item_id, delete: bool) -> Text:
        title, artist, album, path = self._item_fields(item_id)
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

    def _describe_batch(self, item_ids: list, delete: bool) -> Text:
        count = len(item_ids)
        tracks_word = "track" if count == 1 else "tracks"
        text = Text()
        text.append(f"Tuney would like to permanently delete these {count} {tracks_word}:\n\n"
                    if delete else
                    f"Tuney would like to remove these {count} {tracks_word} from your library:\n\n")
        for item_id in item_ids:
            title, artist, _album, path = self._item_fields(item_id)
            text.append("  • ")
            text.append(title, style=self.TITLE_STYLE)
            if artist:
                text.append(f" by {artist}")
            if delete and path:
                text.append("\n    ")
                text.append(path, style=self.PATH_STYLE)
            text.append("\n")
        text.append("\nThe audio files will be deleted from disk — this cannot be undone."
                    if delete else
                    "\nThe audio files will stay on disk.")
        return text

    def _describe_album(self, album_id, delete: bool) -> Text:
        try:
            album = library.get_album(album_id)
        except Exception:
            album = None
        name = f"album {album_id}"
        artist = None
        tracks: list | None = None
        if album is not None:
            name = str(album.album or name)
            artist = str(album.albumartist or "") or None
            tracks = list(album.items())
        text = Text()
        text.append("Tuney would like to permanently delete the album "
                    if delete else "Tuney would like to remove the album ")
        text.append(name, style=self.ALBUM_STYLE)
        if artist:
            text.append(f" by {artist}")
        if not delete:
            text.append(" — from your library")
        if tracks is not None:
            count = len(tracks)
            text.append(f" — all {count} tracks:\n\n" if count != 1 else " — 1 track:\n\n")
            for item in tracks:
                text.append("  • ")
                text.append(str(item.title or f"item {item.id}"), style=self.TITLE_STYLE)
                if delete and item.path:
                    text.append("\n    ")
                    text.append(os.fsdecode(item.path), style=self.PATH_STYLE)
                text.append("\n")
        else:
            text.append(".\n")
        text.append("\nThe audio files and album art will be deleted from disk "
                    "— this cannot be undone."
                    if delete else
                    "\nThe audio files will stay on disk.")
        return text

    def compose(self) -> ComposeResult:
        detail = self._describe()
        if detail is None:
            args = ", ".join(f"{k}={v!r}" for k, v in self._request.get("args", {}).items())
            detail = Text(f"{self._request.get('description') or 'Tool requires approval'}\n\n"
                          f"  {self._request.get('name', '?')}({args})")
        with Container(id="confirm-dialog"):
            yield Label("Tuney needs your approval", id="modal-title")
            with VerticalScroll(id="confirm-detail-scroll", can_focus=False):
                yield Static(detail, id="confirm-detail")
            with Horizontal(id="confirm-buttons"):
                yield Button("Approve (y)", id="approve", variant="error")
                yield Button("Reject (n)", id="reject", variant="primary")
            yield Label(r"\[y] approve | \[n]/\[esc] reject | \[↑↓] scroll", id="modal-hint")

    def on_mount(self) -> None:
        self.query_one("#reject", Button).focus()   # safe default

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "approve")

    def action_scroll_detail(self, direction: int) -> None:
        scroll = self.query_one("#confirm-detail-scroll", VerticalScroll)
        if direction > 0:
            scroll.scroll_down()
        else:
            scroll.scroll_up()

    def action_scroll_detail_page(self, direction: int) -> None:
        scroll = self.query_one("#confirm-detail-scroll", VerticalScroll)
        if direction > 0:
            scroll.scroll_page_down()
        else:
            scroll.scroll_page_up()

    def action_approve(self) -> None:
        self.dismiss(True)

    def action_reject(self) -> None:
        self.dismiss(False)
