from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label, Static


class WishlistDetailModal(ModalScreen):
    """Full details for one wishlist row.

    Mirrors TrackDetailModal's layout, but a wishlist item is a plain dict
    with no file on disk — so there is no cover art to show, just the fields.
    """

    CSS = """
    WishlistDetailModal { align: center middle; }
    #wl-detail-dialog {
        width: 80%;
        max-width: 100;
        height: auto;
        max-height: 80%;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    #wl-detail-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }
    #wl-detail-fields-scroll {
        width: 1fr;
        height: auto;
        max-height: 26;
    }
    #wl-detail-fields { width: 1fr; height: auto; }
    #wl-detail-hint { width: 100%; text-align: center; padding-top: 1; }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
        ("q", "close", "Close"),
        ("enter", "close", "Close"),
    ]

    # (label, dict key) for each field, in display order.
    FIELDS = [
        ("Artist", "artist"),
        ("Title", "title"),
        ("Album", "album"),
        ("Year", "year"),
        ("Status", "status"),
        ("Priority", "priority"),
        ("Notes", "notes"),
        ("MusicBrainz id", "mb_id"),
        ("Added", "date_added"),
        ("Updated", "date_updated"),
    ]

    LABEL_WIDTH = 14

    def __init__(self, item: dict) -> None:
        super().__init__()
        self._item = item

    def compose(self) -> ComposeResult:
        title = str(self._item.get("title") or "") or "Untitled"
        with Container(id="wl-detail-dialog"):
            yield Label(title, id="wl-detail-title")
            with VerticalScroll(id="wl-detail-fields-scroll", can_focus=False):
                yield Static(self._fields_text(), id="wl-detail-fields")
            yield Label(r"\[esc]/\[enter] close | \[↑↓] scroll", id="wl-detail-hint")

    def _fields_text(self) -> Text:
        text = Text()
        for label, key in self.FIELDS:
            value = self._item.get(key)
            if value is None or value == "":
                continue
            text.append(f"{label:>{self.LABEL_WIDTH}}  ", style="bold")
            text.append(f"{value}\n")
        return text

    def action_close(self) -> None:
        self.dismiss()
