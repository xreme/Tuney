from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, Static

from tuney import library
from tuney.wishlist import Wishlist


class AddWishlistItemModal(ModalScreen[int | bool | None]):
    """Add a new wishlist item.

    Beyond the plain fields, this offers MusicBrainz matching: fill in an
    artist/title, hit Match, and pick from the candidates to stamp an mb_id
    (and prefill the metadata). An mb_id typed in directly can be looked up to
    validate and flesh it out. Both MusicBrainz calls hit the network, so they
    run off the UI thread.
    """

    CSS = """
    AddWishlistItemModal { align: center middle; }
    #add-dialog {
        width: 80%;
        max-width: 90;
        height: auto;
        max-height: 90%;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    #add-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }
    #add-fields { height: auto; max-height: 18; }
    #add-fields Label { padding: 0 1; color: $text-muted; }
    #add-fields Input { margin-bottom: 1; }
    #add-status { width: 100%; text-align: center; color: $text-muted; }
    #candidates { height: auto; max-height: 10; margin-top: 1; }
    #candidates.hidden { display: none; }
    #add-buttons { height: auto; align-horizontal: center; padding-top: 1; }
    #add-buttons Button { margin: 0 1; }
    #add-hint { width: 100%; text-align: center; padding-top: 1; }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    # (field key, label, placeholder) for each text input, in display order.
    FIELDS = [
        ("artist", "Artist", "Artist"),
        ("title", "Title", "Title"),
        ("album", "Album", "Album"),
        ("year", "Year", "e.g. 1997"),
        ("mb_id", "MusicBrainz id", "recording id (optional)"),
        ("notes", "Notes", "Notes"),
        ("priority", "Priority", "0"),
        ("status", "Status", "wanted"),
    ]

    # Candidate columns shown after a Match, in display order.
    CANDIDATE_COLUMNS = ["Artist", "Title", "Album", "Year", "Score"]

    def __init__(self) -> None:
        super().__init__()
        self._candidates: list[dict] = []

    def compose(self) -> ComposeResult:
        with Container(id="add-dialog"):
            yield Label("Add to wishlist", id="add-title")
            with VerticalScroll(id="add-fields"):
                for key, label, placeholder in self.FIELDS:
                    yield Label(label)
                    yield Input(placeholder=placeholder, id=f"f-{key}")
            yield Static("", id="add-status")
            yield DataTable(id="candidates", classes="hidden")
            with Horizontal(id="add-buttons"):
                yield Button("Match", id="match")
                yield Button("Look up id", id="lookup")
                yield Button("Add", id="add", variant="primary")
                yield Button("Cancel", id="cancel")
            yield Label(
                r"\[Match] find on MusicBrainz | \[esc] cancel", id="add-hint")

    def on_mount(self) -> None:
        table = self.query_one("#candidates", DataTable)
        table.cursor_type = "row"
        table.add_columns(*self.CANDIDATE_COLUMNS)
        self.query_one("#f-artist", Input).focus()

    # ---- field access ------------------------------------------------------

    def _value(self, key: str) -> str:
        return self.query_one(f"#f-{key}", Input).value.strip()

    def _set(self, key: str, value) -> None:
        self.query_one(f"#f-{key}", Input).value = (
            "" if value is None else str(value))

    def _parse_int(self, key: str) -> int | None:
        raw = self._value(key)
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def _status(self, message: str) -> None:
        self.query_one("#add-status", Static).update(message)

    # ---- MusicBrainz matching ---------------------------------------------

    def action_match(self) -> None:
        artist, title = self._value("artist"), self._value("title")
        if not (artist or title):
            self.notify("Enter an artist or title to match.",
                        severity="warning")
            return
        self._status("Searching MusicBrainz…")
        self._match(artist, title, self._value("album"))

    @work(thread=True, exclusive=True)
    def _match(self, artist: str, title: str, album: str) -> None:
        """Query MusicBrainz off the UI thread — it hits the network."""
        try:
            candidates = library.musicbrainz_candidates(
                artist=artist, title=title, album=album)
        except Exception as error:
            self.app.call_from_thread(self._match_failed, error)
            return
        self.app.call_from_thread(self._show_candidates, candidates or [])

    def _match_failed(self, error: Exception) -> None:
        self._status(f"MusicBrainz lookup failed: {error}")

    def _show_candidates(self, candidates: list[dict]) -> None:
        self._candidates = candidates
        table = self.query_one("#candidates", DataTable)
        table.clear()
        if not candidates:
            self._status("No MusicBrainz matches found.")
            table.add_class("hidden")
            return
        for candidate in candidates:
            score = candidate.get("score")
            table.add_row(
                candidate.get("artist") or "",
                candidate.get("title") or "",
                candidate.get("album") or "",
                candidate.get("year") or "",
                f"{score:.2f}" if isinstance(score, (int, float)) else "",
            )
        self._status("Select a match to fill its details.")
        table.remove_class("hidden")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if not (0 <= event.cursor_row < len(self._candidates)):
            return
        self._fill_from_candidate(self._candidates[event.cursor_row])

    def _fill_from_candidate(self, candidate: dict) -> None:
        self._set("mb_id", candidate.get("mb_id"))
        for key in ("artist", "title", "album", "year"):
            value = candidate.get(key)
            if value:
                self._set(key, value)
        self._status("Filled from MusicBrainz match.")

    # ---- direct mb_id lookup ----------------------------------------------

    def action_lookup(self) -> None:
        mb_id = self._value("mb_id")
        if not mb_id:
            self.notify("Enter a MusicBrainz id to look up.",
                        severity="warning")
            return
        self._status("Looking up recording…")
        self._lookup(mb_id)

    @work(thread=True, exclusive=True)
    def _lookup(self, mb_id: str) -> None:
        try:
            track = library.musicbrainz_track(mb_id)
        except Exception as error:
            self.app.call_from_thread(self._match_failed, error)
            return
        self.app.call_from_thread(self._apply_track, track)

    def _apply_track(self, track: dict | None) -> None:
        if not track:
            self._status("No MusicBrainz recording with that id.")
            return
        for key in ("artist", "title", "album", "year"):
            value = track.get(key)
            if value:
                self._set(key, value)
        self._status("Details filled from MusicBrainz.")

    # ---- submit ------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {
            "match": self.action_match,
            "lookup": self.action_lookup,
            "add": self.action_add,
            "cancel": self.action_cancel,
        }
        handler = actions.get(event.button.id)
        if handler is not None:
            handler()

    def action_add(self) -> None:
        artist, title = self._value("artist"), self._value("title")
        if not (artist or title):
            self.notify("A wishlist item needs at least an artist or title.",
                        severity="warning")
            return
        try:
            new_id = Wishlist(library.DB).add_item(
                artist=artist,
                title=title,
                album=self._value("album"),
                year=self._parse_int("year"),
                mb_id=self._value("mb_id"),
                notes=self._value("notes"),
                priority=self._parse_int("priority") or 0,
                status=self._value("status") or "wanted",
            )
        except Exception as error:
            self.notify(f"Could not add item: {error}", severity="error")
            return
        # Return a truthy result so the pane knows to reload; the new row id
        # once the data layer returns one, otherwise a plain signal.
        self.dismiss(new_id or True)

    def action_cancel(self) -> None:
        self.dismiss(None)
