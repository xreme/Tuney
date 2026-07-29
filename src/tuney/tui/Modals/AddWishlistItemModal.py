from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, Checkbox, DataTable, Label, SelectionList, Static

from tuney import library
from tuney.wishlist import Wishlist
from tuney.tui.Modals.WishlistFormModal import WishlistFormModal


class AddWishlistItemModal(WishlistFormModal):
    """Add wishlist items via MusicBrainz matching.

    Press Match: with a title it searches recordings; with only an album name
    (no title) it searches albums. Pick a recording to fill the fields and Add
    one song. Pick an album to see its songs, then add the whole album or just
    the tracks you check. The searches hit the network, so they run off the UI
    thread.
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
    #candidates { height: auto; max-height: 10; margin-top: 1; }
    #album-tracks { height: auto; max-height: 12; margin-top: 1; }
    #select-all { margin-top: 1; }
    AddWishlistItemModal .hidden { display: none; }
    #add-buttons { height: auto; align-horizontal: center; padding-top: 1; }
    #add-buttons Button { margin: 0 1; }
    #add-hint { width: 100%; text-align: center; padding-top: 1; }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    TRACK_COLUMNS = ["Artist", "Title", "Album", "Year", "Score"]
    ALBUM_COLUMNS = ["Album", "Artist", "Year", "Tracks"]

    def __init__(self) -> None:
        super().__init__()
        self._mode = "manual"          # manual | track | album | album_tracks
        self._candidates: list[dict] = []    # track matches (mode "track")
        self._albums: list[dict] = []        # album matches (mode "album")
        self._album_tracks: list[dict] = []  # songs of the chosen album
        # mb_id/year captured from a chosen recording, stored with the item on
        # Add even though they aren't editable fields.
        self._matched: dict = {}

    def compose(self) -> ComposeResult:
        with Container(id="add-dialog"):
            yield Label("Add to wishlist", id="add-title")
            yield from self.compose_fields()
            yield Static("", id="form-status")
            yield DataTable(id="candidates", classes="hidden")
            yield Checkbox("Add the entire album", value=True,
                           id="select-all", classes="hidden")
            yield SelectionList(id="album-tracks", classes="hidden")
            with Horizontal(id="add-buttons"):
                yield Button("Match", id="match")
                yield Button("Add", id="add", variant="primary")
                yield Button("Add checked", id="add-checked",
                             variant="primary", classes="hidden")
                yield Button("Cancel", id="cancel")
            yield Label(
                r"\[Match] search MusicBrainz — album if no title · \[esc] cancel",
                id="add-hint")

    def on_mount(self) -> None:
        table = self.query_one("#candidates", DataTable)
        table.cursor_type = "row"
        self.query_one("#f-artist").focus()

    # ---- visibility helpers ------------------------------------------------

    def _show(self, widget_id: str, visible: bool) -> None:
        self.query_one(f"#{widget_id}").set_class(not visible, "hidden")

    def _set_album_track_mode(self, on: bool) -> None:
        """Swap the single-item Add button for the album 'Add checked' one."""
        self._show("add", not on)
        self._show("add-checked", on)

    def _hide_album_widgets(self) -> None:
        self._set_album_track_mode(False)
        self._show("select-all", False)
        self._show("album-tracks", False)

    # ---- match dispatch ----------------------------------------------------

    def action_match(self) -> None:
        """Album search when an album but no title is given; track search
        otherwise."""
        artist = self._value("artist")
        title = self._value("title")
        album = self._value("album")
        if album and not title:
            self._status("Searching MusicBrainz for albums…")
            self._album_search(artist, album)
            return
        if not (artist or title):
            self.notify("Enter a title to match, or an album to find a release.",
                        severity="warning")
            return
        self._status("Searching MusicBrainz…")
        self._match(artist, title, album)

    def _match_failed(self, error: Exception) -> None:
        self._status(f"MusicBrainz lookup failed: {error}")

    # ---- track matching ----------------------------------------------------

    @work(thread=True, exclusive=True)
    def _match(self, artist: str, title: str, album: str) -> None:
        try:
            candidates = library.musicbrainz_candidates(
                artist=artist, title=title, album=album)
        except Exception as error:
            self.app.call_from_thread(self._match_failed, error)
            return
        self.app.call_from_thread(self._show_candidates, candidates or [])

    def _show_candidates(self, candidates: list[dict]) -> None:
        self._candidates = candidates
        self._mode = "track"
        self._hide_album_widgets()
        table = self.query_one("#candidates", DataTable)
        table.clear(columns=True)
        table.add_columns(*self.TRACK_COLUMNS)
        if not candidates:
            self._status("No MusicBrainz matches found.")
            self._show("candidates", False)
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
        self._show("candidates", True)

    def _fill_from_candidate(self, candidate: dict) -> None:
        self._matched = {"mb_id": candidate.get("mb_id", ""),
                         "year": candidate.get("year")}
        for key in ("artist", "title", "album"):
            value = candidate.get(key)
            if value:
                self._set(key, value)
        self._status("Filled from MusicBrainz match.")

    # ---- album matching ----------------------------------------------------

    @work(thread=True, exclusive=True)
    def _album_search(self, artist: str, album: str) -> None:
        try:
            albums = library.musicbrainz_albums(artist=artist, album=album)
        except Exception as error:
            self.app.call_from_thread(self._match_failed, error)
            return
        self.app.call_from_thread(self._show_albums, albums or [])

    def _show_albums(self, albums: list[dict]) -> None:
        self._albums = albums
        self._mode = "album"
        self._hide_album_widgets()
        table = self.query_one("#candidates", DataTable)
        table.clear(columns=True)
        table.add_columns(*self.ALBUM_COLUMNS)
        if not albums:
            self._status("No matching albums found.")
            self._show("candidates", False)
            return
        for album in albums:
            table.add_row(
                album.get("album") or "",
                album.get("artist") or "",
                album.get("year") or "",
                str(album.get("track_count") or 0),
            )
        self._status("Select an album to add it or pick its songs.")
        self._show("candidates", True)

    def _enter_album_tracks(self, album: dict) -> None:
        self._album_tracks = album.get("tracks", [])
        self._mode = "album_tracks"
        selection = self.query_one("#album-tracks", SelectionList)
        selection.clear_options()
        selection.add_options([
            (f"{i + 1:>2}. {track.get('title') or '(untitled)'}", i, True)
            for i, track in enumerate(self._album_tracks)
        ])
        self._show("candidates", False)
        self._show("select-all", True)
        self._show("album-tracks", True)
        self.query_one("#select-all", Checkbox).value = True
        self._set_album_track_mode(True)
        self._status(
            f"{album.get('album') or 'Album'} — {len(self._album_tracks)} "
            "songs. Add the entire album, or uncheck the ones you don't want.")
        selection.focus()

    # ---- events ------------------------------------------------------------

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if self._mode == "track" and 0 <= event.cursor_row < len(self._candidates):
            self._fill_from_candidate(self._candidates[event.cursor_row])
        elif self._mode == "album" and 0 <= event.cursor_row < len(self._albums):
            self._enter_album_tracks(self._albums[event.cursor_row])

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id != "select-all":
            return
        selection = self.query_one("#album-tracks", SelectionList)
        if event.value:
            selection.select_all()
        else:
            selection.deselect_all()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handler = {
            "match": self.action_match,
            "add": self.action_add,
            "add-checked": self.action_add_checked,
            "cancel": self.action_cancel,
        }.get(event.button.id)
        if handler is not None:
            handler()

    # ---- submit ------------------------------------------------------------

    def action_add(self) -> None:
        artist, title = self._value("artist"), self._value("title")
        if not (artist or title):
            self.notify("A wishlist item needs at least an artist or title.",
                        severity="warning")
            return
        try:
            with Wishlist(library.DB) as wishlist:
                new_id = wishlist.add_item(
                    artist=artist,
                    title=title,
                    album=self._value("album"),
                    notes=self._value("notes"),
                    mb_id=self._matched.get("mb_id", ""),
                    year=self._matched.get("year"),
                )
        except Exception as error:
            self.notify(f"Could not add item: {error}", severity="error")
            return
        self.dismiss(new_id or True)

    def action_add_checked(self) -> None:
        selected = self.query_one("#album-tracks", SelectionList).selected
        if not selected:
            self.notify("Check at least one song to add.", severity="warning")
            return
        notes = self._value("notes")   # applies to the whole album
        try:
            with Wishlist(library.DB) as wishlist:
                for index in selected:
                    track = self._album_tracks[index]
                    wishlist.add_item(
                        artist=track.get("artist", ""),
                        title=track.get("title", ""),
                        album=track.get("album", ""),
                        year=track.get("year"),
                        mb_id=track.get("mb_id", ""),
                        notes=notes,
                    )
        except Exception as error:
            self.notify(f"Could not add songs: {error}", severity="error")
            return
        self.dismiss(len(selected))

    def action_cancel(self) -> None:
        self.dismiss(None)
