from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Label, Static

from tuney import lastfm


class WishlistDetailModal(ModalScreen):
    """Full details for one wishlist row.

    Mirrors TrackDetailModal's layout, but a wishlist item is a plain dict
    with no file on disk — so instead of the cover art off the file, the extra
    section here is what Last.fm knows about the record: how many people listen
    to it, what it gets tagged as, a blurb and where its cover lives. That is
    the information the user is deciding on ("is this the one I meant, and do I
    still want it?"), and none of it is in the wishlist row itself.

    The lookup is a network call, so it runs off the UI thread and the dialog
    opens without waiting for it. No API key configured means no section — the
    stored fields are shown exactly as before.
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
    #wl-detail-lastfm { width: 1fr; height: auto; padding-top: 1; }
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

    # (label, dict key) for the Last.fm block, same layout as the fields above.
    LASTFM_FIELDS = [
        ("Listeners", "listeners"),
        ("Plays", "playcount"),
        ("Tags", "tags"),
        ("Cover", "image"),
        ("Last.fm", "url"),
    ]

    LABEL_WIDTH = 14
    # Long enough to place the record, short enough not to push the fields off
    # the top of the dialog.
    SUMMARY_LIMIT = 400

    def __init__(self, item: dict) -> None:
        super().__init__()
        self._item = item

    def compose(self) -> ComposeResult:
        title = str(self._item.get("title") or "") or "Untitled"
        with Container(id="wl-detail-dialog"):
            yield Label(title, id="wl-detail-title")
            with VerticalScroll(id="wl-detail-fields-scroll", can_focus=False):
                yield Static(self._fields_text(), id="wl-detail-fields")
                yield Static("", id="wl-detail-lastfm")
            yield Label(r"\[esc]/\[enter] close | \[↑↓] scroll", id="wl-detail-hint")

    def on_mount(self) -> None:
        if lastfm.available():
            self._set_lastfm(Text("Looking the record up on Last.fm…",
                                  style="italic"))
            self._load_lastfm()

    def _fields_text(self) -> Text:
        text = Text()
        for label, key in self.FIELDS:
            value = self._item.get(key)
            if value is None or value == "":
                continue
            text.append(f"{label:>{self.LABEL_WIDTH}}  ", style="bold")
            text.append(f"{value}\n")
        return text

    # ---- Last.fm -----------------------------------------------------------

    @work(thread=True, exclusive=True)
    def _load_lastfm(self) -> None:
        artist = str(self._item.get("artist") or "")
        title = str(self._item.get("title") or "")
        album = str(self._item.get("album") or "")
        if not artist or not (title or album):
            # Last.fm needs an artist plus something to look up; a half-filled
            # row isn't a failure, there is just nothing to ask for.
            self.app.call_from_thread(self._show_lastfm, None, "")
            return
        try:
            # A song when the row names one, otherwise the album it belongs to.
            info = (lastfm.track_info(artist, title) if title
                    else lastfm.album_info(artist, album))
        except lastfm.LastfmError as error:
            self.app.call_from_thread(self._show_lastfm, None, str(error))
            return
        self.app.call_from_thread(self._show_lastfm, info, "")

    def _show_lastfm(self, info: dict | None, error: str) -> None:
        if error:
            self._set_lastfm(Text(f"Last.fm lookup failed: {error}",
                                  style="italic"))
            return
        if not info:
            self._set_lastfm(Text("Last.fm has nothing on this record.",
                                  style="italic"))
            return
        self._set_lastfm(self._lastfm_text(info))

    def _lastfm_text(self, info: dict) -> Text:
        text = Text()
        text.append("\nFrom Last.fm\n", style="bold")
        for label, key in self.LASTFM_FIELDS:
            value = info.get(key)
            if not value:
                continue
            if key == "tags":
                value = ", ".join(value[:5])
            elif isinstance(value, int):
                value = f"{value:,}"
            text.append(f"{label:>{self.LABEL_WIDTH}}  ", style="bold")
            text.append(f"{value}\n")
        summary = info.get("summary") or ""
        if summary:
            if len(summary) > self.SUMMARY_LIMIT:
                summary = summary[:self.SUMMARY_LIMIT].rstrip() + "…"
            text.append(f"\n{summary}\n", style="italic")
        return text

    def _set_lastfm(self, text: Text) -> None:
        try:
            self.query_one("#wl-detail-lastfm", Static).update(text)
        except NoMatches:
            pass       # dialog closed while the lookup was in flight

    def action_close(self) -> None:
        self.dismiss()
